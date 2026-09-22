import atexit
import gc
import csv
import multiprocessing as mp
import os
import re
import signal
import sys
import threading
import time
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from queue import Queue, Empty
from lxml import html as _lxml_html

# Pool compartilhado para parsear HTML em paralelo (lxml libera o GIL no C core)
_parse_pool = ThreadPoolExecutor(
    max_workers=min(16, (os.cpu_count() or 4) * 2),
    thread_name_prefix="html-parse",
)


def _ts():
    """Timestamp HH:MM:SS.mmm para ver paralelismo no output."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════
#  PAINEL DE CONTROLE — mude o TIER para escalar
#
#  1 processo por site. Cada processo tem:
#    - 1 Chrome próprio (memória isolada, zero contaminação)
#    - N listing threads + M detail workers
#    - 1 FetchCoordinator local (sem tab switching)
#
#  TIER    max_sites  L-threads  D-workers  BATCH_SIZE  ~RAM/site
#  normal      2         4          10          10       ~300MB
#  fast        3         6          15          10       ~300MB
#  turbo       4         8          20          10       ~300MB
#  insane      5        10          25          10       ~300MB
#  fire       13        12          30          10       ~300MB
# ══════════════════════════════════════════════════════════════

TIER = "insane"  # <── MUDE AQUI

_TIER_CONFIG = {
    "normal": dict(
        sites=2,
        listing_threads=4,
        detail_workers=10,
        max_fetch=300,
        batch_window=0.15,
        batch_size=10,
    ),
    "fast": dict(
        sites=3,
        listing_threads=6,
        detail_workers=15,
        max_fetch=400,
        batch_window=0.12,
        batch_size=10,
    ),
    "turbo": dict(
        sites=4,
        listing_threads=8,
        detail_workers=20,
        max_fetch=500,
        batch_window=0.10,
        batch_size=10,
    ),
    "insane": dict(
        sites=5,
        listing_threads=10,
        detail_workers=25,
        max_fetch=600,
        batch_window=0.08,
        batch_size=10,
    ),
    "fire": dict(
        sites=13,
        listing_threads=12,
        detail_workers=30,
        max_fetch=800,
        batch_window=0.06,
        batch_size=10,
    ),
}

_cfg = _TIER_CONFIG.get(TIER, _TIER_CONFIG["fast"])

SITES_IN_PARALLEL = _cfg["sites"]
N_LISTING_THREADS = _cfg["listing_threads"]
N_DETAIL_WORKERS = _cfg["detail_workers"]
MAX_FETCH = _cfg["max_fetch"]  # URLs por Promise.all call
BATCH_WINDOW = _cfg[
    "batch_window"
]  # segundos coletando requests antes de disparar
BATCH_SIZE = _cfg["batch_size"]
LISTING_PAGE_CHUNK = 10  # páginas por submissão
QUEUE_LOG_CLEANUP_INTERVAL = 200  # salva a cada N produtos, reescreve o txt

# ═══ NAO MEXER ═══
SITES_FILE = "sites.json"
LIMIT_ITEMS = 0
PAGE_LOAD_TIMEOUT = 60
DRIVER_START_RETRIES = 5
DRIVER_START_RETRY_DELAY = 3
MAX_HTML_SIZE = 500_000
EXCLUDED_SITE_BRANDS = {
    "audi",
    "bmw",
    "gm",
    "honda",
    "kia",
    "mitsubishi",
    "nissan",
    "toyota",
}
PROJECT_ROOT = Path(__file__).resolve().parent


# ── Chrome binary — detectado automaticamente por plataforma ──
def _find_chrome():
    import platform

    _os = platform.system()
    if _os == "Windows":
        candidates = [
            Path(os.environ.get("ProgramW6432", r"C:\Program Files"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ]
    elif _os == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        ]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
            Path("/snap/bin/chromium"),
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


CHROME_BINARY = _find_chrome()


def _find_chrome_profile():
    import platform

    _os = platform.system()
    if _os == "Windows":
        return (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google"
            / "Chrome"
            / "User Data"
        )
    elif _os == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Google"
            / "Chrome"
        )
    else:
        return Path.home() / ".config" / "google-chrome"


CHROME_PROFILE_SOURCE = _find_chrome_profile()
CHROME_PROFILE_COPY = PROJECT_ROOT / "chrome_profile"

print(f"\n{'='*60}")
print(f"  CONFIG: Tier={TIER.upper()} — MULTI-PROCESS (1 Chrome/site)")
print(
    f"  Até {SITES_IN_PARALLEL} sites × {N_DETAIL_WORKERS} detail workers = {SITES_IN_PARALLEL * N_DETAIL_WORKERS} fetches paralelos"
)
print(f"  Memória isolada por processo (~{SITES_IN_PARALLEL * 300}MB total)")
print(
    f"  Promise.all: até {MAX_FETCH} URLs por call | window={int(BATCH_WINDOW*1000)}ms"
)
print(f"{'='*60}\n")


# ─────────────────────────── RetryPolicy ────────────────────────────


class RetryPolicy:
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        self.backoff_seconds = [1, 3, 9]
        self._retry_queues = {}
        self._lock = threading.Lock()

    def should_retry(self, url, error_type, attempt=0):
        if attempt >= self.max_retries:
            return False
        if error_type in ["permanent"]:
            return False
        if error_type in ["transient", "network", "cloudflare"]:
            return True
        return False

    def get_backoff_delay(self, attempt):
        if attempt < len(self.backoff_seconds):
            return self.backoff_seconds[attempt]
        return self.backoff_seconds[-1]

    def add_retry(self, site_url, url):
        with self._lock:
            if site_url not in self._retry_queues:
                self._retry_queues[site_url] = {}
            if url not in self._retry_queues[site_url]:
                self._retry_queues[site_url][url] = 0

    def get_retries(self, site_url):
        with self._lock:
            urls = list(self._retry_queues.get(site_url, {}).keys())
            if site_url in self._retry_queues:
                del self._retry_queues[site_url]
            return urls

    def increment_attempt(self, site_url, url):
        with self._lock:
            if (
                site_url in self._retry_queues
                and url in self._retry_queues[site_url]
            ):
                self._retry_queues[site_url][url] += 1


# ─────────────────────────── RateLimiter ────────────────────────────

import random


class RateLimiter:
    def __init__(
        self, jitter_ms=100, target_latency_ms=500, target_error_rate=0.05
    ):
        self.jitter_ms = jitter_ms
        self.target_latency_ms = target_latency_ms
        self.target_error_rate = target_error_rate
        self._metrics = {}
        self._lock = threading.Lock()

    def record_fetch(self, site_url, latency_ms, error=False):
        with self._lock:
            if site_url not in self._metrics:
                self._metrics[site_url] = {
                    "latencies": [],
                    "errors": 0,
                    "total": 0,
                    "throttled": False,
                }
            self._metrics[site_url]["latencies"].append(latency_ms)
            if error:
                self._metrics[site_url]["errors"] += 1
            self._metrics[site_url]["total"] += 1

    def should_throttle(self, site_url):
        with self._lock:
            if site_url not in self._metrics:
                return False
            m = self._metrics[site_url]
            if m["total"] < 10:
                return False
            return (m["errors"] / m["total"]) > 0.10

    def get_jitter(self):
        std = self.jitter_ms * 0.5
        return max(1, int(random.gauss(self.jitter_ms, std)))

    def adapt_batch_window(self, site_url, current_window):
        with self._lock:
            if (
                site_url not in self._metrics
                or len(self._metrics[site_url]["latencies"]) < 5
            ):
                return current_window
            m = self._metrics[site_url]
            latencies = m["latencies"][-20:]
            avg_latency = sum(latencies) / len(latencies)
            error_rate = m["errors"] / max(1, m["total"])
            if (
                avg_latency < self.target_latency_ms
                and error_rate < self.target_error_rate
            ):
                return min(current_window + 0.02, 0.20)
            if (
                avg_latency > self.target_latency_ms * 1.5
                or error_rate > self.target_error_rate
            ):
                return max(current_window - 0.02, 0.05)
            return current_window

    def get_metrics_summary(self, site_url):
        with self._lock:
            if site_url not in self._metrics:
                return "N/A"
            m = self._metrics[site_url]
            if m["total"] == 0:
                return "N/A"
            latencies = m["latencies"][-20:]
            avg_lat = sum(latencies) / len(latencies) if latencies else 0
            error_rate = (m["errors"] / m["total"]) * 100
            return f"lat={avg_lat:.0f}ms err={error_rate:.1f}%"


# ─────────────────────────── SiteStats ────────────────────────────


class SiteStats:
    def __init__(self, site_url):
        self.site_url = site_url
        self.listed = 0
        self.saved = 0
        self.failed = 0
        self.not_found = 0
        self.cloudflare_blocks = 0
        self.rate_limited = 0
        self.last_fetch_latency_ms = 0
        self.start_time = time.time()
        self.last_batch_time = self.start_time
        self._lock = threading.Lock()

    def increment(self, key, count=1):
        with self._lock:
            if hasattr(self, key):
                setattr(self, key, getattr(self, key) + count)

    def get_stats_dict(self):
        with self._lock:
            return {
                "listed": self.listed,
                "saved": self.saved,
                "failed": self.failed,
                "not_found": self.not_found,
                "cloudflare_blocks": self.cloudflare_blocks,
                "rate_limited": self.rate_limited,
            }

    def get_progress(self, total_estimated=None):
        with self._lock:
            if total_estimated:
                pct = (
                    (self.saved / total_estimated * 100)
                    if total_estimated > 0
                    else 0
                )
                return f"[{self.saved}/{total_estimated} | {pct:.0f}%]"
            return f"[{self.saved} saved]"

    def get_rate(self):
        with self._lock:
            elapsed = time.time() - self.start_time
            return self.saved / (elapsed / 60.0) if elapsed > 0 else 0

    def get_eta_seconds(self, total_estimated):
        rate = self.get_rate()
        if rate <= 0:
            return None
        with self._lock:
            remaining = total_estimated - self.saved
            return remaining / rate * 60 if remaining > 0 else 0


class CloudflareBlockedException(Exception):
    pass


# ─────────────────────────── driver registry + Ctrl+C ────────────────────────────

_drivers_registry: list = []
_registry_lock = threading.Lock()


def _register_driver(driver):
    with _registry_lock:
        _drivers_registry.append(driver)


def _unregister_driver(driver):
    with _registry_lock:
        try:
            _drivers_registry.remove(driver)
        except ValueError:
            pass


def _kill_all_drivers():
    with _registry_lock:
        for d in list(_drivers_registry):
            try:
                d.quit()
            except Exception:
                pass
        _drivers_registry.clear()


def _sigint_handler(sig, frame):
    print("\n[Ctrl+C] Encerrando — matando todos os processos Chrome...")
    _kill_all_drivers()
    sys.exit(0)


signal.signal(signal.SIGINT, _sigint_handler)
atexit.register(_kill_all_drivers)


# ─────────────────────────── helpers ────────────────────────────

import json as _json


def load_sites(json_file):
    try:
        with open(json_file, "r") as f:
            return _json.load(f)
    except FileNotFoundError:
        print(f"Error: {json_file} not found.")
        return []


def filter_sites(sites):
    filtered, skipped = [], []
    for site_url in sites:
        brand = urlparse(site_url).netloc.lower().split(".", 1)[0]
        if brand in EXCLUDED_SITE_BRANDS:
            skipped.append(site_url)
        else:
            filtered.append(site_url)
    if skipped:
        print(f"Sites ignorados: {skipped}")
    return filtered


def get_chrome_version_main():
    import platform, subprocess

    try:
        if not CHROME_BINARY or not os.path.exists(CHROME_BINARY):
            return None
        if platform.system() == "Windows":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Item '{CHROME_BINARY}').VersionInfo.ProductVersion",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(
                [CHROME_BINARY, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
        version_output = (result.stdout or result.stderr or "").strip()
        match = re.search(r"(\d+)\.", version_output)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def ensure_chrome_profile_copy():
    if CHROME_PROFILE_COPY.exists():
        return CHROME_PROFILE_COPY
    if not CHROME_PROFILE_SOURCE.exists():
        return None

    def ignore_chrome_cache(_, names):
        ignored = {
            "Cache",
            "Code Cache",
            "Crashpad",
            "BrowserMetrics",
            "component_crx_cache",
            "DawnGraphiteCache",
            "DawnWebGPUCache",
            "GraphiteDawnCache",
            "GPUCache",
            "GrShaderCache",
            "Safe Browsing",
            "ShaderCache",
            "Session Storage",
            "blob_storage",
            "optimization_guide_model_store",
            "optimization_guide_hint_cache_store",
            "segmentation_platform",
        }
        return [name for name in names if name in ignored]

    shutil.copytree(
        CHROME_PROFILE_SOURCE, CHROME_PROFILE_COPY, ignore=ignore_chrome_cache
    )
    return CHROME_PROFILE_COPY


def get_profile_directory_name(profile_root):
    try:
        with open(profile_root / "Local State", "r", encoding="utf-8") as f:
            data = _json.load(f)
        return data.get("profile", {}).get("last_used") or "Default"
    except Exception:
        return "Default"


_session_profiles: list[Path] = []


def create_chrome_session_profile(base_profile):
    session_profile = Path(tempfile.mkdtemp(prefix="whitelabel_chrome_"))
    shutil.copytree(base_profile, session_profile, dirs_exist_ok=True)
    _session_profiles.append(session_profile)
    return session_profile


def cleanup_session_profiles():
    for p in _session_profiles:
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
    _session_profiles.clear()


atexit.register(cleanup_session_profiles)


# ─────────────────────────── CSV ────────────────────────────

_csv_lock = threading.Lock()


def get_csv_filename(site_url):
    domain = urlparse(site_url).netloc
    return f"products_{domain.replace('.', '_')}.csv"


def get_queue_log_filename(site_url):
    domain = urlparse(site_url).netloc
    return f"queue_{domain.replace('.', '_')}.txt"


def load_processed_from_csv(csv_filename):
    processed = set()
    if not os.path.exists(csv_filename):
        return processed
    try:
        with open(csv_filename, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                u = row.get("URL", "")
                if u:
                    processed.add(u)
    except Exception:
        pass
    return processed


def load_queue_log(queue_log_file):
    queued = set()
    if not os.path.exists(queue_log_file):
        return queued
    try:
        with open(queue_log_file, "r", encoding="utf-8") as f:
            for line in f:
                u = line.strip()
                if u:
                    queued.add(u)
    except Exception:
        pass
    return queued


class QueueLogBuffer:
    def __init__(self, queue_log_file):
        self.queue_log_file = queue_log_file
        self._buffer = set()
        self._saved = set()
        self._lock = threading.Lock()

    def set_buffer(self, urls):
        with self._lock:
            self._buffer = set(urls)

    def append_url(self, url):
        with self._lock:
            self._buffer.add(url)

    def mark_saved(self, url):
        with self._lock:
            self._saved.add(url)

    def cleanup_immediate(self):
        with self._lock:
            current_buffer = self._buffer
            current_saved = self._saved
            self._buffer = set()
            self._saved = set()

        if not os.path.exists(self.queue_log_file) and not current_buffer:
            return 0

        try:
            existing = set()
            if os.path.exists(self.queue_log_file):
                with open(self.queue_log_file, "r", encoding="utf-8") as f:
                    existing = {l.strip() for l in f if l.strip()}

            all_urls = existing | current_buffer
            pending = all_urls - current_saved

            with open(self.queue_log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(pending) + ("\n" if pending else ""))

            return len(pending)
        except Exception as e:
            print(f"[queue-log cleanup erro] {e}")
            with self._lock:
                self._buffer.update(current_buffer)
                self._saved.update(current_saved)
            return -1


def cleanup_queue_log(queue_log_file, saved_urls):
    if not os.path.exists(queue_log_file):
        return
    try:
        with open(queue_log_file, "r", encoding="utf-8") as f:
            lines = {l.strip() for l in f if l.strip()}
        pending = lines - saved_urls
        with open(queue_log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(pending) + ("\n" if pending else ""))
    except Exception as e:
        print(f"[queue-log cleanup erro] {e}")


def save_product_to_csv(product, filename):
    if "URL" in product and len(product["URL"]) > 2000:
        product["URL"] = product["URL"][:2000]

    if "Name" in product:
        product["Name"] = product["Name"].upper() if product["Name"] else ""

    if "Brand" in product and product["Brand"]:
        bu = product["Brand"].upper()
        product["Brand"] = "HONDA" if "HONDA" in bu else bu

    if "Manufacturer" in product and product["Manufacturer"]:
        mu = product["Manufacturer"].upper()
        product["Manufacturer"] = "HONDA" if "HONDA" in mu else mu

    if "Year_Subtitle" in product and product["Year_Subtitle"]:
        m = re.search(r"^(\d{4}(?:-\d{4})?)", product["Year_Subtitle"].strip())
        if m:
            product["Year_Subtitle"] = m.group(1)

    if "Images" in product:
        if isinstance(product["Images"], list) and product["Images"]:
            fixed = []
            for img in product["Images"]:
                if img.startswith("//"):
                    fixed.append(f"https:{img}")
                elif img.startswith("http"):
                    fixed.append(img)
            product["Images"] = str(fixed)
        else:
            product["Images"] = "[]"

    if "Applications" in product:
        if isinstance(product["Applications"], list):
            product["Applications"] = (
                str(product["Applications"])
                if product["Applications"]
                else "[]"
            )
        else:
            product["Applications"] = "[]"

    flat = {k: str(v) if v else "" for k, v in product.items()}

    with _csv_lock:
        file_exists = os.path.isfile(filename)
        with open(filename, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(flat)


# ─────────────────────────── driver factory ────────────────────────────


def _make_chrome_options(session_profile):
    options = uc.ChromeOptions()
    options.page_load_strategy = "eager"
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--js-flags=--expose-gc")
    if CHROME_BINARY:
        options.binary_location = CHROME_BINARY
    options.add_experimental_option(
        "prefs",
        {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.fonts": 2,
        },
    )
    if session_profile is not None:
        options.add_argument(
            f"--profile-directory={get_profile_directory_name(session_profile)}"
        )
    return options


def create_driver(headless=False):
    profile_copy = ensure_chrome_profile_copy()
    chrome_version = get_chrome_version_main()

    last_error = None
    for attempt in range(1, DRIVER_START_RETRIES + 1):
        session_profile = (
            create_chrome_session_profile(profile_copy)
            if profile_copy
            else None
        )
        options = _make_chrome_options(session_profile)

        chrome_kwargs = {
            "options": options,
            "headless": headless,
            "use_subprocess": True,
        }
        if CHROME_BINARY:
            chrome_kwargs["browser_executable_path"] = CHROME_BINARY
        if session_profile is not None:
            chrome_kwargs["user_data_dir"] = str(session_profile)
        if chrome_version is not None:
            chrome_kwargs["version_main"] = chrome_version

        try:
            driver = uc.Chrome(**chrome_kwargs)
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT + 60)
            driver.set_script_timeout(60)
            driver.implicitly_wait(5)
            _register_driver(driver)
            return driver
        except Exception as e:
            last_error = e
            print(
                f"[Driver] Falha ao iniciar Chrome (tentativa {attempt}/{DRIVER_START_RETRIES}): {str(e)[:160]}"
            )
            if attempt < DRIVER_START_RETRIES:
                time.sleep(DRIVER_START_RETRY_DELAY)
    raise last_error


# ─────────────────────────── browser fetch JS ────────────────────────────

_BATCH_FETCH_JS = """
var callback = arguments[arguments.length - 1];
var urls = Array.from(arguments).slice(0, arguments.length - 1);
var results = {};
var i = 0;
var BATCH = 3;

function next() {
    if (i >= urls.length) {
        try { gc(); } catch(e) {}
        callback(results);
        return;
    }
    var chunk = urls.slice(i, i + BATCH);
    i += BATCH;
    var promises = chunk.map(function(url) {
        return fetch(url, {
            credentials: 'include',
            headers: { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' }
        })
        .then(function(r) { return r.ok ? r.text() : ''; })
        .catch(function() { return ''; })
        .then(function(html) {
            if (html && html.length > 100) results[url] = html;
        });
    });
    Promise.all(promises).then(function() { next(); });
}
next();
"""

_BATCH_FETCH_TIMEOUT_JS = """
var callback = arguments[arguments.length - 1];
var urls = Array.from(arguments).slice(0, arguments.length - 1);
var results = {};
var i = 0;
var BATCH = 3;
var TIMEOUT = 30000;

function next() {
    if (i >= urls.length) {
        try { gc(); } catch(e) {}
        callback(results);
        return;
    }
    var chunk = urls.slice(i, i + BATCH);
    i += BATCH;
    var promises = chunk.map(function(url) {
        var ctrl = new AbortController();
        var tid = setTimeout(function() { ctrl.abort(); }, TIMEOUT);
        return fetch(url, {
            credentials: 'include',
            headers: { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' },
            signal: ctrl.signal
        })
        .then(function(r) { clearTimeout(tid); return r.ok ? r.text() : ''; })
        .catch(function() { clearTimeout(tid); return ''; })
        .then(function(html) {
            if (html && html.length > 100) results[url] = html;
        });
    });
    Promise.all(promises).then(function() { next(); });
}
next();
"""

_FETCH_JS = """
var callback = arguments[arguments.length - 1];
fetch(arguments[0], {
    credentials: 'include',
    headers: { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' }
})
.then(r => {
    if (!r.ok) return callback({error: 'HTTP_' + r.status, html: ''});
    return r.text().then(html => callback({error: null, html: html}));
})
.catch(e => callback({error: e.message, html: ''}));
"""

_CF_MARKERS = (
    "verify you are human",
    "challenge-running",
    "cf_chl_opt",
    "turnstile",
)


def _clean_html(html, url=None, debug=False):
    if not html:
        return None
    if len(html) < 100:
        return None
    html_start = html[:2000]
    for marker in _CF_MARKERS:
        if marker in html_start:
            return None
    if len(html) > MAX_HTML_SIZE:
        return html[:MAX_HTML_SIZE]
    return html


def _is_cloudflare_blocked(html):
    """Check if HTML is a Cloudflare challenge page."""
    if not html or len(html) < 100:
        return False
    html_start = html[:2000]
    return any(marker in html_start for marker in _CF_MARKERS)


# ─────────────────────────── FetchCoordinator (per-site) ────────────────────────────
#
# Cada site tem seu próprio FetchCoordinator.
# SEM TabManager — 1 Chrome por site, direto no driver.
# SEM lock global — cada processo é independente.


class FetchCoordinator:
    _MAX_CHUNK = 3

    def __init__(
        self,
        driver,
        site_url,
        max_fetch=MAX_FETCH,
        batch_window=BATCH_WINDOW,
        retry_policy=None,
        rate_limiter=None,
        stats=None,
    ):
        self.driver = driver
        self.site_url = site_url
        self.max_fetch = max_fetch
        self.batch_window = batch_window
        self.retry_policy = retry_policy
        self.rate_limiter = rate_limiter
        self.stats = stats
        self._q = Queue()
        self._stop = threading.Event()
        self._lock = (
            threading.Lock()
        )  # Protege execute_async_script (Selenium não é thread-safe)
        self._t = threading.Thread(
            target=self._run, daemon=True, name="fetch-coord"
        )
        driver.set_script_timeout(60)
        self._current_batch_window = batch_window
        self._t.start()

    def fetch(self, urls):
        if not urls:
            return {}
        out = {}
        done = threading.Event()
        self._q.put(("listing", list(urls), out, done))
        done.wait(timeout=70)  # 60s script + margem
        return out

    def fetch_priority(self, urls):
        if not urls:
            return {}
        out = {}
        done = threading.Event()
        self._q.put(("detail", list(urls), out, done))
        done.wait(timeout=70)  # 60s script + margem
        return out

    def stop(self):
        self._stop.set()

    def _exec(self, urls, priority=False):
        """Executa fetch em chunks. SEM switch_to — driver já está no site certo.
        Detecta bloqueios Cloudflare e faz refresh + retry automático."""
        html_map = {}
        cf_blocked_urls = []
        total_chunks = 0

        for i in range(0, len(urls), self._MAX_CHUNK):
            chunk = urls[i : i + self._MAX_CHUNK]
            total_chunks += 1

            try:
                # Rate limiting: jitter antes do fetch
                if self.rate_limiter:
                    jitter = self.rate_limiter.get_jitter()
                    time.sleep(jitter / 1000.0)

                with self._lock:
                    t_start = time.time()
                    raw = self.driver.execute_async_script(
                        _BATCH_FETCH_TIMEOUT_JS, *chunk
                    )
                    latency_ms = (time.time() - t_start) * 1000

                # Registra métrica
                if self.rate_limiter:
                    self.rate_limiter.record_fetch(
                        self.site_url, latency_ms, error=False
                    )
                if self.stats and priority:
                    self.stats.increment("last_fetch_latency_ms", latency_ms)

                if raw:
                    for url, html in raw.items():
                        if _is_cloudflare_blocked(html):
                            cf_blocked_urls.append(url)
                        else:
                            cleaned = _clean_html(html)
                            if cleaned:
                                html_map[url] = cleaned

                del raw
                gc.collect()

            except MemoryError:
                gc.collect()
                if len(chunk) > 1:
                    mid = max(1, len(chunk) // 2)
                    print(
                        f"  [{_ts()}] [{self.site_url}] MemoryError com {len(chunk)} URLs, dividindo..."
                    )
                    html_map.update(self._exec(chunk[:mid], priority))
                    html_map.update(self._exec(chunk[mid:], priority))
                else:
                    print(
                        f"  [{_ts()}] [{self.site_url}] MemoryError irrecuperável ({len(chunk)} URL)"
                    )

            except Exception as e:
                err_type = type(e).__name__
                err_msg = str(e).strip()[:120]
                print(
                    f"  [{_ts()}] [{self.site_url}] fetch erro: [{err_type}] {err_msg}"
                )

        # ── Recovery: se QUALQUER fetch foi CF-bloqueado, refresh + retry só os bloqueados ──
        if cf_blocked_urls:
            print(
                f"  [{_ts()}] [{self.site_url}] Cloudflare bloqueou {len(cf_blocked_urls)} URLs. Refreshing..."
            )
            try:
                with self._lock:
                    self.driver.refresh()
                time.sleep(5)

                # Retry APENAS as URLs CF-bloqueadas
                for i in range(0, len(cf_blocked_urls), self._MAX_CHUNK):
                    chunk = cf_blocked_urls[i : i + self._MAX_CHUNK]
                    try:
                        with self._lock:
                            raw = self.driver.execute_async_script(
                                _BATCH_FETCH_TIMEOUT_JS, *chunk
                            )
                        if raw:
                            for url, html in raw.items():
                                cleaned = _clean_html(html)
                                if cleaned:
                                    html_map[url] = cleaned
                        del raw
                        gc.collect()
                    except Exception:
                        pass

                recovered = len([u for u in cf_blocked_urls if u in html_map])
                if recovered:
                    print(
                        f"  [{_ts()}] [{self.site_url}] CF recovery OK: {recovered}/{len(cf_blocked_urls)} URLs recuperadas"
                    )
                else:
                    print(
                        f"  [{_ts()}] [{self.site_url}] CF recovery falhou: 0/{len(cf_blocked_urls)} URLs após refresh"
                    )

            except Exception as e:
                print(
                    f"  [{_ts()}] [{self.site_url}] CF refresh falhou: {str(e)[:80]}"
                )

        return html_map

    def _run(self):
        """
        Thread principal do coordinator.
        PRIORIDADE: detail requests processados ANTES de listing.
        """
        while not self._stop.is_set():
            # ── Fase 1: Drenar priority requests (detail) ──
            pending = []
            while True:
                try:
                    item = self._q.get_nowait()
                    pending.append(item)
                except Empty:
                    break

            if pending:
                # Verifica se há mais detail requests em 50ms
                t_end = time.time() + 0.05
                while time.time() < t_end:
                    try:
                        item = self._q.get_nowait()
                        pending.append(item)
                    except Empty:
                        time.sleep(0.002)
            else:
                # ── Fase 2: Sem detail → espera listing ──
                try:
                    first = self._q.get(timeout=0.5)
                except Empty:
                    continue
                pending = [first]
                t_end = time.time() + self._current_batch_window
                while time.time() < t_end:
                    try:
                        pending.append(self._q.get_nowait())
                    except Empty:
                        time.sleep(0.005)

            if not pending:
                continue

            # Separar detail vs listing
            detail_items = [
                (u, o, d) for p, u, o, d in pending if p == "detail"
            ]
            listing_items = [
                (u, o, d) for p, u, o, d in pending if p == "listing"
            ]

            # Processar detail primeiro
            if detail_items:
                all_detail_urls = []
                for urls, out, done in detail_items:
                    all_detail_urls.extend(urls)
                if all_detail_urls:
                    # Batch cap
                    if len(all_detail_urls) > self.max_fetch:
                        all_detail_urls = all_detail_urls[: self.max_fetch]
                    html_map = self._exec(all_detail_urls, priority=True)
                    for urls, out, done in detail_items:
                        for u in urls:
                            if u in html_map:
                                out[u] = html_map[u]
                        filled = sum(1 for u in urls if u in out)
                        if filled == 0 and len(urls) > 0:
                            print(
                                f"  [{_ts()}] [{self.site_url}] AVISO: pediu {len(urls)} detail URLs, 0 válidos"
                            )
                        done.set()

            # Processar listing
            if listing_items:
                all_listing_urls = []
                for urls, out, done in listing_items:
                    all_listing_urls.extend(urls)
                if all_listing_urls:
                    # Coleta durante batch_window
                    t_end = time.time() + self._current_batch_window
                    while time.time() < t_end:
                        try:
                            p2, u2, o2, d2 = self._q.get_nowait()
                            if p2 == "listing":
                                listing_items.append((u2, o2, d2))
                                all_listing_urls.extend(u2)
                        except Empty:
                            time.sleep(0.005)

                    # Batch cap
                    if len(all_listing_urls) > self.max_fetch:
                        all_listing_urls = all_listing_urls[: self.max_fetch]

                    html_map = self._exec(all_listing_urls, priority=False)
                    for urls, out, done in listing_items:
                        for u in urls:
                            if u in html_map:
                                out[u] = html_map[u]
                        filled = sum(1 for u in urls if u in out)
                        if filled == 0 and len(urls) > 0:
                            print(
                                f"  [{_ts()}] [{self.site_url}] AVISO: pediu {len(urls)} listing URLs, 0 válidos"
                            )
                        done.set()


# ─────────────────────────── HTML Parsing ────────────────────────────


def parse_listing_page(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    product_urls = [
        urljoin(base_url, link.get("href", ""))
        for link in soup.select(".product-title .title-link")
        if link.get("href")
    ]
    next_page = None
    next_btn = soup.select_one(
        ".search-pagination .paginator li a i.fa-angle-right"
    )
    if next_btn:
        parent_a = next_btn.find_parent("a")
        if parent_a and parent_a.get("href"):
            next_page = urljoin(base_url, parent_a["href"])
    return product_urls, next_page


def parse_product_detail(html, url):
    try:
        tree = _lxml_html.fromstring(html)
    except Exception as e:
        print(f"  [parse] lxml error {url[:60]}: {str(e)[:80]}")
        return None

    def _txt(*xpaths):
        for xp in xpaths:
            try:
                els = tree.xpath(xp)
                if els:
                    t = els[0].text_content().strip()
                    if t:
                        return t
            except Exception:
                pass
        return ""

    product = {"URL": url}
    product["Name"] = _txt('//*[contains(@class,"product-title")]')
    product["PartNumber"] = _txt(
        '//*[contains(@class,"sku-display")]',
        '//*[contains(@class,"catalog-product-id")]',
    )
    product["Brand"] = _txt(
        '//*[contains(@class,"product-manufacturer-name")]',
        '//*[contains(@class,"part-manufacturer")]//strong',
    )
    product["Year_Subtitle"] = _txt('//*[contains(@class,"product-subtitle")]')
    product["Manufacturer"] = _txt('//*[contains(@class,"part-manufacturer")]')

    images = []
    try:
        for el in tree.xpath('//*[contains(@class,"product-main-image")]'):
            src = el.get("src", "")
            if src:
                images.append(src)
        for el in tree.xpath('//*[contains(@class,"product-secondary-image")]'):
            img_url = el.get("data-image-main-url") or el.get("href", "")
            if img_url and "javascript" not in img_url:
                images.append(img_url)
        product["Images"] = list(set(images))
    except Exception:
        product["Images"] = []

    applications = []
    try:
        for row in tree.xpath(
            '//*[contains(@class,"fitment-table-body")]'
            '//*[contains(@class,"fitment-row")]'
        ):
            cols = row.xpath(".//td")
            if len(cols) >= 5:
                d = [c.text_content().strip() for c in cols]
                applications.append(f"{d[0]} {d[1]} {d[2]} ({d[3]}) - {d[4]}")
        product["Applications"] = applications
    except Exception:
        product["Applications"] = []

    if not product["Name"] and not product["PartNumber"]:
        return None

    return product


def parse_category_pagination_info(html):
    soup = BeautifulSoup(html, "lxml")
    label = soup.select_one(".search-pagination .pagination-label")
    if not label:
        return None, None
    return label.get("data-pageid"), label.get("data-pageurl")


def extract_next_page_number(html):
    soup = BeautifulSoup(html, "lxml")
    next_btn = soup.select_one(
        ".search-pagination .paginator li a i.fa-angle-right"
    )
    if next_btn:
        parent_a = next_btn.find_parent("a")
        if parent_a and parent_a.get("href"):
            m = re.search(r"[?&]page=(\d+)", parent_a["href"])
            if m:
                return int(m.group(1))
    return None


def discover_categories_from_html(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    categories = []

    def _add(href):
        if not href or href.startswith("#") or "javascript" in href:
            return
        full = urljoin(base_url, href)
        if full not in seen:
            seen.add(full)
            categories.append(full)

    # ── Fonte 1: menu de navegação antigo ──
    for h3 in soup.select("div.themeMegaMenuChildRow h3"):
        if "Parts" in h3.get_text():
            parent = h3.find_parent("div")
            if parent:
                for a in parent.select("ul li a"):
                    _add(a.get("href", ""))
    if not categories:
        for a in soup.select(".themeMegaMenuChildList02 li a"):
            _add(a.get("href", ""))

    # ── Fonte 2: CFC subcategorias ──
    cfc_root = soup.select_one(".cfc_cats_list") or soup
    for a in cfc_root.select("a.subcategory[href]"):
        _add(a.get("href", ""))

    return categories


_MAX_DEEP_LINKS = 30


def deep_discover_listing_urls(coord, url, site_url, _depth=0, _max_depth=3):
    if _depth >= _max_depth:
        return {}

    html_map = coord.fetch([url])
    html = html_map.get(url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")

    if soup.select(".product-title .title-link"):
        return {url: html}

    child_urls = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href or href.startswith("#") or "javascript" in href:
            continue
        full = urljoin(url, href)
        if urlparse(full).netloc != urlparse(site_url).netloc:
            continue
        if full not in seen:
            seen.add(full)
            child_urls.append(full)

    if not child_urls:
        return {}

    if len(child_urls) > _MAX_DEEP_LINKS:
        child_urls = child_urls[:_MAX_DEEP_LINKS]

    child_html = coord.fetch(child_urls)

    result = {}
    for child_url in child_urls:
        child_page = child_html.get(child_url)
        if not child_page:
            continue
        child_soup = BeautifulSoup(child_page, "lxml")
        if child_soup.select(".product-title .title-link"):
            result[child_url] = child_page
        elif _depth + 1 < _max_depth:
            sub = deep_discover_listing_urls(
                coord, child_url, site_url, _depth + 1, _max_depth
            )
            result.update(sub)
        child_html[child_url] = None

    del child_html
    gc.collect()
    return result


# ─────────────────────────── browser fetch helpers ────────────────────────────


def browser_fetch(driver, url):
    """Fetch simples (1 URL). Retorna HTML ou None."""
    try:
        result = driver.execute_async_script(_FETCH_JS, url)
        if not result or result.get("error"):
            return None
        return _clean_html(result.get("html", ""))
    except Exception:
        return None


# ─────────────────────────── process_site (per-site, runs in own process) ────────────────────────────


def process_site(site_url, backlog_barrier=None):
    """
    Processa UM site com SEU PRÓPRIO Chrome driver.
    Chamado via multiprocessing.Process — cada site tem processo + Chrome isolados.
    """
    csv_filename = get_csv_filename(site_url)
    queue_log_file = get_queue_log_filename(site_url)
    qlog = QueueLogBuffer(queue_log_file)

    retry_policy = RetryPolicy(max_retries=3)
    rate_limiter = RateLimiter(
        jitter_ms=100, target_latency_ms=500, target_error_rate=0.05
    )
    stats = SiteStats(site_url)

    processed = load_processed_from_csv(csv_filename)
    print(f"[{site_url}] {len(processed)} URLs já processadas (CSV)")

    queued_log = load_queue_log(queue_log_file)
    pending_from_log = queued_log - processed
    already_done_in_log = queued_log & processed

    if queued_log:
        cleanup_queue_log(queue_log_file, processed)
        print(
            f"[{site_url}] queue log: {len(queued_log)} linhas → "
            f"{len(already_done_in_log)} já no CSV removidas, "
            f"{len(pending_from_log)} pendentes mantidas"
        )
    if pending_from_log:
        print(
            f"[{site_url}] {len(pending_from_log)} URLs pendentes → re-enfileirando imediatamente"
        )

    # ─── Criar Chrome PRÓPRIO para este site ───
    print(f"[{site_url}] Iniciando Chrome dedicado...")
    driver = create_driver(headless=False)
    driver.get(site_url)
    time.sleep(60)

    # Verificar Cloudflare
    cf_blocked = False
    try:
        title = driver.title
        if any(
            msg in title
            for msg in ["Just a moment", "Access denied", "Attention Required!"]
        ):
            cf_blocked = True
    except Exception:
        pass

    if cf_blocked:
        print(f"[{site_url}] [CF] Bloqueado. Resolva o CAPTCHA...")
        input(f"[{site_url}] Pressione Enter após resolver CAPTCHA: ")
        driver.refresh()
        time.sleep(3)
        if any(
            msg in driver.title
            for msg in ["Just a moment", "Access denied", "Attention Required!"]
        ):
            print(f"[{site_url}] Ainda bloqueado — pulando site.")
            try:
                driver.quit()
            except Exception:
                pass
            return

    # ─── Coordinator local (sem TabManager, sem lock global) ───
    coord = FetchCoordinator(
        driver,
        site_url,
        retry_policy=retry_policy,
        rate_limiter=rate_limiter,
        stats=stats,
    )

    # ─── Discovery ───
    print(f"[{site_url}] Descobrindo categorias...")
    categories = []
    html_map = coord.fetch([site_url])
    html = html_map.get(site_url)
    if html:
        categories = discover_categories_from_html(html, site_url)

    if not categories:
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        '//div[contains(@class,"themeMegaMenuChildRow")][.//h3[contains(text(),"Parts")]]//ul//li//a',
                    )
                )
            )
            for el in driver.find_elements(
                By.XPATH,
                '//div[contains(@class,"themeMegaMenuChildRow")][.//h3[contains(text(),"Parts")]]//ul//li//a',
            ):
                href = el.get_attribute("href") or ""
                if href:
                    categories.append(urljoin(site_url, href))
        except TimeoutException:
            pass

    if not categories:
        print(f"[{site_url}] Nenhuma categoria. Pulando.")
        try:
            driver.quit()
        except Exception:
            pass
        return

    # CFC categories (/c)
    cfc_url = site_url.rstrip("/") + "/c"
    cfc_map = coord.fetch([cfc_url])
    cfc_html = cfc_map.get(cfc_url)
    if cfc_html:
        cfc_cats = discover_categories_from_html(cfc_html, site_url)
        existing = set(categories)
        added = [c for c in cfc_cats if c not in existing]
        if added:
            categories.extend(added)
            print(f"[{site_url}] +{len(added)} categorias CFC (/c) descobertas")

    print(f"[{site_url}] {len(categories)} categorias no total (nav + CFC).")

    # ─── Backlog ───
    backlog_urls = []
    if pending_from_log:
        _expected = urlparse(site_url).netloc
        clean_backlog = [
            u for u in pending_from_log if urlparse(u).netloc == _expected
        ]
        cross_count = len(pending_from_log) - len(clean_backlog)
        if cross_count > 0:
            print(
                f"[{_ts()}] [{site_url}] ⚠ {cross_count} URLs cross-site removidas do backlog"
            )
        backlog_urls = clean_backlog

    # ─── Estado de pipeline ───
    prod_url_queue = Queue()
    limit_counter = {"count": 0}
    pipeline_stats_lock = threading.Lock()
    pipeline_stats = {"listed": 0, "listing_done": False}
    stop_event = threading.Event()

    # ─── Enfileirar backlog ───
    if backlog_urls:
        print(
            f"[{_ts()}] [{site_url}] ★ {len(backlog_urls)} URLs em backlog → processamento paralelo"
        )
        for url in backlog_urls:
            prod_url_queue.put(url)
            processed.add(url)
        qlog.set_buffer(backlog_urls)

    _expected_netloc = urlparse(site_url).netloc

    def push_urls_to_queue(urls):
        new_urls = []
        filtered_cross = 0
        with pipeline_stats_lock:
            for u in urls:
                if urlparse(u).netloc != _expected_netloc:
                    filtered_cross += 1
                    continue
                if u not in processed:
                    processed.add(u)
                    prod_url_queue.put(u)
                    new_urls.append(u)
        if filtered_cross > 0:
            sample = [
                u for u in urls if urlparse(u).netloc != _expected_netloc
            ][:3]
            print(
                f"  [{_ts()}] [{site_url}] [push_urls] ⚠ {filtered_cross} URLs cross-site IGNORADAS. Amostra: {sample}"
            )
        for u in new_urls:
            qlog.append_url(u)
        with pipeline_stats_lock:
            pipeline_stats["listed"] += len(new_urls)
        return len(new_urls)

    # ═══════════════════════════════════════════
    # DETAIL WORKERS
    # ═══════════════════════════════════════════

    def _save_product(product):
        try:
            save_product_to_csv(product, csv_filename)
        except Exception as e:
            print(f"  [{_ts()}] [{site_url}] [Saved] CSV error: {str(e)[:80]}")
            stats.increment("failed")
            return

        url = product.get("URL", "")
        with pipeline_stats_lock:
            limit_counter["count"] += 1
            count = limit_counter["count"]
        stats.increment("saved")
        qlog.mark_saved(url)
        pnum = product.get("PartNumber", "?")
        metrics = rate_limiter.get_metrics_summary(site_url)
        rate = stats.get_rate()
        print(
            f"  [{_ts()}] [{site_url}] [Saved] {count} | {metrics} | {rate:.0f} itens/min | fila:{prod_url_queue.qsize()} ({pnum})"
        )
        if count % QUEUE_LOG_CLEANUP_INTERVAL == 0:
            qlog.cleanup_immediate()

    def _process_detail_batch(urls):
        if not urls:
            return
        t_batch = time.time()
        try:
            html_map = coord.fetch_priority(urls)
        except Exception as e:
            elapsed = (time.time() - t_batch) * 1000
            print(
                f"  [{_ts()}] [{site_url}] [Detail] ERROR em coord.fetch({len(urls)} urls): {str(e)[:100]} [{elapsed:.0f}ms]"
            )
            stats.increment("failed", len(urls))
            return

        elapsed = (time.time() - t_batch) * 1000
        if not html_map:
            sample_url = urls[0] if urls else "N/A"
            print(
                f"  [{_ts()}] [{site_url}] [Detail] batch de {len(urls)}: 0 HTMLs [{elapsed:.0f}ms]. Amostra: {sample_url[:80]}"
            )
            stats.increment("failed", len(urls))
            return

        saved_count = len([u for u, h in html_map.items() if h])
        print(
            f"  [{_ts()}] [{site_url}] [Detail] batch de {len(urls)}: {saved_count} HTMLs válidos [{elapsed:.0f}ms]"
        )

        futures = {
            _parse_pool.submit(parse_product_detail, html, url): url
            for url, html in html_map.items()
        }
        del html_map
        gc.collect()

        for future in as_completed(futures):
            url = futures[future]
            try:
                product = future.result()
            except Exception as e:
                print(
                    f"  [{_ts()}] [{site_url}] [Detail] parse error {url[:50]}: {str(e)[:60]}"
                )
                stats.increment("failed")
                continue
            if product:
                _save_product(product)
            else:
                stats.increment("not_found")
        futures.clear()
        gc.collect()

    def detail_worker(worker_id):
        batch = []
        while not stop_event.is_set():
            if LIMIT_ITEMS > 0 and limit_counter["count"] >= LIMIT_ITEMS:
                print(
                    f"  [{_ts()}] [{site_url}] [Worker-{worker_id}] limit atingido"
                )
                break
            try:
                url = prod_url_queue.get(timeout=2)
            except Empty:
                if batch:
                    _process_detail_batch(batch)
                    batch = []
                with pipeline_stats_lock:
                    if pipeline_stats["listing_done"]:
                        break
                continue
            if url is None:
                if batch:
                    _process_detail_batch(batch)
                    batch = []
                prod_url_queue.task_done()
                print(
                    f"  [{_ts()}] [{site_url}] [Worker-{worker_id}] stopped (sentinel)"
                )
                break
            batch.append(url)
            if len(batch) >= BATCH_SIZE:
                _process_detail_batch(batch)
                batch = []
            prod_url_queue.task_done()
        if batch:
            _process_detail_batch(batch)
        print(f"  [{_ts()}] [{site_url}] [Worker-{worker_id}] exited")

    print(f"[{site_url}] Iniciando {N_DETAIL_WORKERS} detail workers...")
    detail_threads = []
    for i in range(N_DETAIL_WORKERS):
        t = threading.Thread(
            target=detail_worker, args=(i,), daemon=True, name=f"detail-{i}"
        )
        t.start()
        detail_threads.append(t)

    # ═══════════════════════════════════════════
    # LISTING
    # ═══════════════════════════════════════════

    def process_category(cat_url):
        if stop_event.is_set():
            return 0

        html_map = coord.fetch([cat_url])
        html = html_map.get(cat_url)
        if not html:
            return 0

        urls, _ = parse_listing_page(html, cat_url)

        # Deep discovery se 0 produtos
        if not urls:
            soup_dbg = BeautifulSoup(html, "lxml")
            year_links = soup_dbg.select(
                "#vehicle-data-lists a[href], .vehicle-column a[href]"
            )
            if year_links:
                cat_name = cat_url.rstrip("/").split("/")[-1]
                print(
                    f"  [{_ts()}] [{site_url}] [Deep] {cat_name}: {len(year_links)} links de ano/trim → buscando part categories..."
                )
                listing_pages = deep_discover_listing_urls(
                    coord, cat_url, site_url
                )
                if listing_pages:
                    print(
                        f"  [{_ts()}] [{site_url}] [Deep] {cat_name}: encontrou {len(listing_pages)} listing pages com produtos"
                    )
                    total_pushed = 0
                    for listing_url, listing_html in listing_pages.items():
                        page_urls, _ = parse_listing_page(
                            listing_html, listing_url
                        )
                        total_pushed += push_urls_to_queue(page_urls)
                    return total_pushed
                else:
                    print(
                        f"  [{_ts()}] [{site_url}] [Deep] {cat_name}: nenhuma listing page encontrada"
                    )

        items_per_page = len(urls) if urls else 12

        # AJAX count
        page_id, page_url_slug = parse_category_pagination_info(html)
        total_pages = None
        cat_count = None
        if page_id and page_url_slug:
            parsed_base = urlparse(cat_url)
            ajax_url = (
                f"{parsed_base.scheme}://{parsed_base.netloc}/ajax/dynamic-seo-search"
                f"?page=1&page_id={page_id}&page_url={page_url_slug}"
                f"&catalog_type=parts&identifier%5BusePreviousFacets%5D=true"
                f"&pUrl={page_url_slug}&load_facets=0"
            )
            ajax_map = coord.fetch([ajax_url])
            ajax_raw = ajax_map.get(ajax_url, "")
            m = re.search(r'"count"\s*:\s*(\d+)', ajax_raw)
            if m:
                cat_count = int(m.group(1))
                ipp = items_per_page if items_per_page > 0 else 12
                total_pages = (cat_count + ipp - 1) // ipp

        pushed = push_urls_to_queue(urls)

        cat_name = cat_url.rstrip("/").split("/")[-1]
        pages_info = (
            f" | {cat_count} itens ~{total_pages}pgs" if cat_count else ""
        )
        metrics = rate_limiter.get_metrics_summary(site_url)
        with pipeline_stats_lock:
            listed_total = pipeline_stats["listed"]
        print(
            f"  [{_ts()}] [{site_url}] [Listing] {cat_name}: +{pushed} URLs | total:{listed_total} | {metrics} | fila:{prod_url_queue.qsize()}{pages_info}"
        )

        next_num = extract_next_page_number(html)
        if total_pages and total_pages > 1:
            page_nums = list(range(2, total_pages + 1))
        elif next_num and next_num > 1:
            page_nums = list(range(2, min(next_num + 200, 2000) + 1))
        else:
            page_nums = []

        if page_nums and not stop_event.is_set():
            base_cat = re.sub(r"[?&]page=\d+", "", cat_url)
            sep = "&" if "?" in cat_url else "?"

            batch_new = 0
            total_chunks = (
                len(page_nums) + LISTING_PAGE_CHUNK - 1
            ) // LISTING_PAGE_CHUNK

            for chunk_i in range(0, len(page_nums), LISTING_PAGE_CHUNK):
                if stop_event.is_set():
                    break
                chunk_page_nums = page_nums[
                    chunk_i : chunk_i + LISTING_PAGE_CHUNK
                ]
                chunk_urls = [
                    f"{base_cat}{sep}page={n}" for n in chunk_page_nums
                ]

                html_map = coord.fetch(chunk_urls)

                chunk_new = 0
                for pg_url, page_html in html_map.items():
                    page_urls, _ = parse_listing_page(page_html, pg_url)
                    chunk_new += push_urls_to_queue(page_urls)

                batch_new += chunk_new

                chunk_num = chunk_i // LISTING_PAGE_CHUNK + 1
                if chunk_new > 0 or chunk_num == total_chunks:
                    metrics = rate_limiter.get_metrics_summary(site_url)
                    with pipeline_stats_lock:
                        listed_total = pipeline_stats["listed"]
                    print(
                        f"  [{_ts()}] [{site_url}] [Listing] {cat_name} [{chunk_num}/{total_chunks}]: +{chunk_new} | total:{batch_new} | {metrics} | fila:{prod_url_queue.qsize()}"
                    )

            pushed += batch_new

        return pushed

    listing_queue = Queue()

    def listing_thread_worker(thread_id):
        while not stop_event.is_set():
            try:
                cat_url = listing_queue.get(timeout=1)
            except Empty:
                continue
            try:
                process_category(cat_url)
            except Exception as e:
                print(f"  [{site_url}] [Listing] Erro em {cat_url}: {e}")
            gc.collect()
            listing_queue.task_done()

    listing_threads = []
    for i in range(N_LISTING_THREADS):
        t = threading.Thread(
            target=listing_thread_worker,
            args=(i,),
            daemon=True,
            name=f"listing-{i}",
        )
        t.start()
        listing_threads.append(t)

    # ═══ ESPERAR BACKLOG ANTES DE LISTING ═══
    if backlog_urls:
        print(
            f"[{_ts()}] [{site_url}] Aguardando backlog ({len(backlog_urls)} URLs) ser processado..."
        )
        while not stop_event.is_set():
            qsize = prod_url_queue.qsize()
            if qsize == 0:
                print(f"[{_ts()}] [{site_url}] Backlog zerado.")
                break
            time.sleep(2)
    else:
        print(f"[{_ts()}] [{site_url}] Sem backlog. Aguardando outros sites...")

    # ═══ BARRIER: TODOS os sites devem terminar backlog antes de listing ═══
    if backlog_barrier:
        print(
            f"[{_ts()}] [{site_url}] Backlog pronto. Aguardando barreira ({backlog_barrier.parties} sites)..."
        )
        try:
            backlog_barrier.wait(timeout=600)  # max 10 min esperando
            print(
                f"[{_ts()}] [{site_url}] Barreira liberada! Iniciando listing."
            )
        except Exception as e:
            print(
                f"[{_ts()}] [{site_url}] Barreira timeout/erro: {e}. Iniciando listing mesmo assim."
            )

    # ═══ CICLOS DE LISTING ═══
    cycle = 0
    consecutive_empty = 0

    while not stop_event.is_set():
        cycle += 1
        print(f"\n[{site_url}] [{_ts()}] === Ciclo {cycle} de listing ===")
        for cat_url in categories:
            listing_queue.put(cat_url)
        with pipeline_stats_lock:
            prev_listed = pipeline_stats["listed"]
        listing_queue.join()
        gc.collect()
        with pipeline_stats_lock:
            new_found = pipeline_stats["listed"] - prev_listed
        consecutive_empty = 0 if new_found > 0 else consecutive_empty + 1
        rate = stats.get_rate()
        metrics = rate_limiter.get_metrics_summary(site_url)
        print(
            f"[{site_url}] [{_ts()}] Ciclo {cycle}: +{new_found} URLs | total_listed:{pipeline_stats['listed']} | saved:{stats.saved} | {rate:.0f} itens/min | {metrics} | fila={prod_url_queue.qsize()}"
        )
        if consecutive_empty >= 2:
            print(
                f"[{site_url}] [{_ts()}] Listing esgotado apos {consecutive_empty} ciclos vazios."
            )
            break

    stop_event.set()
    coord.stop()
    with pipeline_stats_lock:
        pipeline_stats["listing_done"] = True
    print(
        f"\n[{site_url}] [{_ts()}] [Listing] FINALIZADO. {pipeline_stats['listed']} URLs listadas, {stats.saved} salvos."
    )
    print(
        f"[{site_url}] [{_ts()}] Aguardando fila ({prod_url_queue.qsize()} pendentes)..."
    )

    try:
        prod_url_queue.join()
    except KeyboardInterrupt:
        pass

    for _ in range(N_DETAIL_WORKERS):
        prod_url_queue.put(None)
    for t in detail_threads:
        t.join(timeout=30)

    qlog.cleanup_immediate()

    # ─── Fechar Chrome ───
    try:
        driver.quit()
    except Exception:
        pass

    # ─── Resumo final ───
    elapsed_sec = time.time() - stats.start_time
    elapsed_min = elapsed_sec / 60.0
    final_stats = stats.get_stats_dict()
    rate_final = stats.get_rate()

    print(f"\n[{site_url}] [{_ts()}] ════════════════════════════════════════")
    print(
        f"[{site_url}] Conclusão em {elapsed_min:.1f}min ({elapsed_sec:.0f}s)"
    )
    print(
        f"[{site_url}] Salvos: {stats.saved} | Falhados: {final_stats['failed']} | Não-encontrados: {final_stats['not_found']}"
    )
    print(
        f"[{site_url}] Cloudflare blocks: {final_stats['cloudflare_blocks']} | Rate-limited: {final_stats['rate_limited']}"
    )
    print(f"[{site_url}] Taxa média: {rate_final:.1f} itens/min")
    print(f"[{site_url}] ════════════════════════════════════════")


# ─────────────────────────── main (multi-process) ────────────────────────────


def _run_batch(sites_batch, batch_num, total_batches):
    """
    Executa um lote de sites em paralelo (cada um no seu processo).
    Retorna lista de sites que falharam.
    """
    print(f"\n{'#'*60}")
    print(f"#  LOTE {batch_num}/{total_batches}: {len(sites_batch)} sites")
    print(
        f"#  Sites: {[urlparse(s).netloc.split('.')[0] for s in sites_batch]}"
    )
    print(f"{'#'*60}\n")

    # Barrier: todos os sites do lote devem terminar backlog antes de listing
    backlog_barrier = mp.Barrier(len(sites_batch))

    processes = []
    for site_url in sites_batch:
        p = mp.Process(
            target=process_site,
            args=(site_url, backlog_barrier),
            daemon=True,
            name=f"site-{urlparse(site_url).netloc}",
        )
        p.start()
        processes.append((site_url, p))
        print(f"[{_ts()}] Processo iniciado: {site_url} (PID={p.pid})")
        time.sleep(
            2
        )  # Stagger: evitar picos de CPU na inicialização simultânea

    print(
        f"\n[{_ts()}] {len(processes)} processos rodando. Aguardando conclusão do lote {batch_num}...\n"
    )

    failed_sites = []
    for site_url, p in processes:
        p.join()
        if p.exitcode != 0:
            print(f"\n[ERRO] {site_url} saiu com código {p.exitcode}")
            failed_sites.append(site_url)
        else:
            print(f"\n=== {site_url} CONCLUIDO ===")

    return failed_sites


def main():
    try:
        with open(SITES_FILE) as f:
            sites = _json.load(f)
    except FileNotFoundError:
        print(f"Nenhum site carregado de {SITES_FILE}")
        return

    sites = filter_sites(sites)
    if not sites:
        print("Nenhum site restante apos filtro de exclusao.")
        return

    total_sites = len(sites)
    print(f"Sites carregados: {sites}")
    print(f"Total: {total_sites} sites — 1 processo + 1 Chrome por site")

    # Dividir em lotes de SITES_IN_PARALLEL
    batch_size = SITES_IN_PARALLEL if SITES_IN_PARALLEL else total_sites
    batches = [
        sites[i : i + batch_size] for i in range(0, total_sites, batch_size)
    ]
    total_batches = len(batches)

    print(f"\n{'='*60}")
    print(
        f"  {total_sites} sites em {total_batches} lote(s) de até {batch_size}"
    )
    print(f"  RAM por lote: ~{batch_size * 300}MB")
    print(
        f"  Total detail workers por lote: {batch_size} × {N_DETAIL_WORKERS} = {batch_size * N_DETAIL_WORKERS}"
    )
    print(f"{'='*60}\n")

    all_failed = []

    for batch_num, batch in enumerate(batches, 1):
        failed = _run_batch(batch, batch_num, total_batches)
        all_failed.extend(failed)

        if batch_num < total_batches:
            print(
                f"\n[{_ts()}] Lote {batch_num}/{total_batches} finalizado. "
                f"Iniciando próximo lote em 3s..."
            )
            time.sleep(3)

    # Retry de sites que falharam (1 tentativa extra)
    retry_failed = []
    if all_failed:
        print(f"\n{'='*60}")
        print(
            f"  RETRY: {len(all_failed)} site(s) falharam — tentando novamente"
        )
        print(f"  Sites: {[urlparse(s).netloc for s in all_failed]}")
        print(f"{'='*60}\n")
        retry_failed = _run_batch(all_failed, "RETRY", 1)
        if retry_failed:
            print(
                f"\n⚠ Sites que continuam falhando após retry: {[urlparse(s).netloc for s in retry_failed]}"
            )

    # Resumo final
    n_ok = total_sites - len(retry_failed)
    print(f"\n{'='*60}")
    print(f"  TODOS OS {total_sites} SITES PROCESSADOS")
    print(f"  OK: {n_ok} | Falharam: {len(retry_failed)}")
    if retry_failed:
        print(
            f"  Sites com falha: {[urlparse(s).netloc for s in retry_failed]}"
        )
    print(f"{'='*60}")


if __name__ == "__main__":
    # Windows multiprocessing: spawn (evita pickling issues com objetos complexos)
    mp.set_start_method("spawn", force=True)
    main()
