import ctypes
import re
import sys
import time

import pyautogui
import pyscreeze
from PIL import ImageGrab

# pyautogui.locateCenterOnScreen() only ever screenshots the PRIMARY monitor
# (pyscreeze's screenshot(region=None) call never passes allScreens=True), so
# on a multi-monitor setup a button on the second monitor is invisible to it
# — not a confidence/match problem, the pixels just aren't in the search
# image at all. These helpers grab the full virtual screen instead.

_IS_WINDOWS = sys.platform == "win32"

# print() is block-buffered (not line-buffered) whenever stdout is redirected
# to a file/pipe instead of a real terminal, which is exactly what happens
# when this script runs as a background task — nothing shows up in the log
# until the process exits. Force line buffering so log() output is visible
# while the bot is still running.
try:
    sys.stdout.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    pass


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}")


# pyscreeze raises ImageNotFoundException("...highest confidence = 0.NNN")
# even on a miss — it already computed the best match score, it just didn't
# clear the threshold. Capturing that number is the difference between "the
# button genuinely wasn't there" and "it was there but rendered just
# differently enough to fall short" (DPI/zoom/anti-aliasing drift).
_CONFIDENCE_RE = re.compile(r"highest confidence = ([\d.]+)")


def _virtual_screen_origin():
    """Top-left corner of the combined multi-monitor desktop, in screen coords."""
    if not _IS_WINDOWS:
        return 0, 0
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    return user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN)


def locate_center_all_screens(image_paths, confidence=0.8, region=None):
    """
    Like pyautogui.locateCenterOnScreen, but searches every monitor and
    accepts one or more reference images for the same button — useful when
    the button renders slightly differently across pages/zoom levels and a
    single template doesn't always match. Tries each image in order against
    one shared screenshot and returns the first hit.

    image_paths:  a single path, or a list/tuple of paths, to try in order.
    region:       optional (left, top, width, height) in real screen
                  coordinates (same coordinate space pyautogui.click() uses).

    Returns (location, matched_image, best_scores):
      location:     (x, y) in real screen coordinates, or None if no image
                    cleared the confidence threshold.
      matched_image: the image_path that matched, or None.
      best_scores:  {image_path: best confidence score seen for it}, for
                    every image that did NOT match — diagnostic data so a
                    near-miss (e.g. 0.79 against a 0.8 threshold) can be
                    told apart from "nothing there at all" (e.g. 0.3).
    """
    if isinstance(image_paths, (str, bytes)):
        image_paths = [image_paths]

    origin_x, origin_y = _virtual_screen_origin()
    screenshot = ImageGrab.grab(all_screens=True)

    search_image = screenshot
    crop_left, crop_top = 0, 0
    if region is not None:
        left, top, width, height = region
        crop_left, crop_top = left - origin_x, top - origin_y
        search_image = screenshot.crop(
            (crop_left, crop_top, crop_left + width, crop_top + height)
        )

    best_scores = {}
    for image_path in image_paths:
        try:
            box = pyscreeze.locate(image_path, search_image, confidence=confidence)
        except pyscreeze.ImageNotFoundException as exc:
            box = None
            match = _CONFIDENCE_RE.search(str(exc))
            if match:
                best_scores[str(image_path)] = float(match.group(1))
        if box is not None:
            match_left, match_top, match_width, match_height = box
            center_x_in_shot = crop_left + match_left + match_width / 2
            center_y_in_shot = crop_top + match_top + match_height / 2
            location = (int(origin_x + center_x_in_shot), int(origin_y + center_y_in_shot))
            return location, image_path, best_scores

    return None, None, best_scores


def click_at_position(x, y):
    """Move the mouse to (x, y) and click."""
    print(f"Clicking at ({x}, {y})")
    pyautogui.click(x, y)


def wait_for_image_and_click(image_path, confidence=0.8, click_at=None, repeat=False, poll_interval=0.5, timeout=None, region=None, click_delay=0, miss_tolerance=3, retry_interval=3):
    """
    Waits until a specific image appears anywhere on the desktop — including
    secondary monitors — then clicks.

    image_path:   path (or list of paths) to the small screenshot(s) (.png) of
                  the button to detect. Pass several variants of the same
                  button if its rendering isn't always pixel-identical.
    confidence:   0-1 match tolerance (needs opencv-python). Lower it if a slightly
                  different rendering (antialiasing, scaling) keeps it from matching.
    click_at:     None -> click the center of the found image.
                  (x, y) -> ignore the match location and click this fixed point instead.
    repeat:       False -> click once and stop.
                  True  -> keep watching and click every time the button becomes
                  available again (waits for it to disappear first so one
                  appearance doesn't trigger multiple clicks). Stop with Ctrl+C.
    poll_interval: seconds between screen checks.
    timeout:      None -> wait forever. Otherwise give up after this many seconds
                  and return False.
    region:       optional (left, top, width, height) in real screen coordinates
                  to search only part of the desktop — faster and avoids false
                  matches elsewhere. Can extend into a secondary monitor.
    click_delay:  seconds to wait, after the button first appears, before the
                  bot clicks it — a grace period so you have time to fill in
                  the form yourself first. If you submit manually before this
                  elapses (the button disappears), the bot's pending click is
                  cancelled instead of firing on a stale/gone target. 0 keeps
                  the old instant-click behaviour.
    miss_tolerance: consecutive scans the button is allowed to briefly not
                  match before it's considered gone (e.g. the mouse cursor
                  landing on top of it right after a click, or a one-frame
                  redraw glitch, can make a single scan miss even though the
                  button never actually left). Without this, one missed scan
                  resets the "already clicked" state and immediately re-arms
                  another click on the very next scan — which is what
                  produces rapid repeat-clicking on a button that only
                  really appeared once. Raise it if you still see repeats,
                  lower it (min 1) if it feels slow to notice the button is
                  really gone.
    retry_interval: if the button stays continuously visible (never dips
                  out, not even briefly) for this many seconds after the
                  bot already clicked it, click it again. Handles the case
                  where a click didn't actually resolve anything on the page
                  (submit failed silently, etc.) and the exact same button
                  just sits there — without this, the bot would consider it
                  "already handled" forever and never click it again even
                  though it's still sitting there available.
    """
    log(f"Waiting for {image_path!r} to become available on screen (all monitors)...")
    start = time.time()
    visible_since = None
    clicked_this_appearance = False
    last_click_time = None
    miss_streak = 0
    last_diagnostic_log = 0.0

    while True:
        if timeout is not None and (time.time() - start) > timeout:
            log(f"Timed out after {timeout}s waiting for '{image_path}'.")
            return False

        location, matched_image, best_scores = locate_center_all_screens(
            image_path, confidence=confidence, region=region
        )
        now = time.time()

        if location is not None:
            miss_streak = 0
            if visible_since is None:
                visible_since = now
                clicked_this_appearance = False
                last_click_time = None
                log(f"Button appeared (matched {matched_image!r}).")
                if click_delay > 0:
                    log(f"Waiting up to {click_delay}s in case you handle it yourself...")

            should_click = (
                not clicked_this_appearance and (now - visible_since) >= click_delay
            ) or (
                clicked_this_appearance and (now - last_click_time) >= retry_interval
            )

            if should_click:
                target = click_at if click_at is not None else location
                if clicked_this_appearance:
                    log(f"Still visible {retry_interval}s after the last click — retrying at {target}...")
                else:
                    log(f"Clicking at {target} (matched {matched_image!r})...")
                pyautogui.click(target)
                clicked_this_appearance = True
                last_click_time = now
                if not repeat:
                    return True
        else:
            if visible_since is not None:
                miss_streak += 1
                if miss_streak >= miss_tolerance:
                    if not clicked_this_appearance:
                        log("Button disappeared before the grace period elapsed — assuming you handled it, skipping click.")
                    visible_since = None
                    clicked_this_appearance = False
                    last_click_time = None
                    miss_streak = 0
            # Diagnostic only: every ~2s while idle, log the best score each
            # template got even though it didn't clear the threshold. A
            # near-miss (close to `confidence`) points at a rendering-drift
            # problem; scores way below it mean the button just isn't on
            # screen at all right now.
            if best_scores and (now - last_diagnostic_log) >= 2.0:
                scores_str = ", ".join(f"{img}={score:.3f}" for img, score in best_scores.items())
                log(f"(idle) best match scores so far: {scores_str} (threshold {confidence})")
                last_diagnostic_log = now

        time.sleep(poll_interval)


if __name__ == "__main__":
    print("--- Bot de Automação de Mouse Iniciado ---")

    # Fotos do botão (coloque os arquivos nesta mesma pasta). Pode ter mais
    # de uma variante — o bot testa todas a cada varredura e usa a primeira
    # que bater, útil se o botão não renderiza sempre pixel-a-pixel igual.
    BUTTON_IMAGES = ["botao.png", "botao2.png"]

    # 0 = clica IMEDIATAMENTE assim que o botão ficar disponível (é uma
    # corrida por vaga, então velocidade de clique importa aqui). A
    # "tolerância à demora" é o tempo de ESPERA pelo botão aparecer, que já é
    # ilimitado (timeout=None abaixo) — o bot não desiste de esperar, não
    # importa quanto tempo passe até o botão surgir.
    CLICK_DELAY_SECONDS = 0

    # Cada varredura (todos os monitores) leva ~0.15s. Um poll_interval baixo
    # faz o bot varrer de novo quase sem pausa, minimizando o atraso entre o
    # botão aparecer na tela e o bot perceber isso.
    POLL_INTERVAL_SECONDS = 0.05

    # Se o botão continuar aparecendo sem sumir da tela por mais que esse
    # tempo depois do último clique, clica de novo — cobre o caso do clique
    # não ter resolvido nada (ex.: envio falhou) e o mesmo botão continuar
    # lá parado, disponível, sem o bot perceber que precisa tentar de novo.
    RETRY_INTERVAL_SECONDS = 3

    # Fica rodando em loop, sem prazo pra desistir de esperar o botão surgir:
    # clica no instante em que ele aparecer em qualquer monitor, cobrindo as
    # janelas do Chrome nas portas 9222 e 9223. Pare com Ctrl+C.
    wait_for_image_and_click(
        BUTTON_IMAGES,
        repeat=True,
        click_delay=CLICK_DELAY_SECONDS,
        timeout=None,
        poll_interval=POLL_INTERVAL_SECONDS,
        retry_interval=RETRY_INTERVAL_SECONDS,
    )

    print("--- Script finalizado ---")
