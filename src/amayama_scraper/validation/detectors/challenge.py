"""Detector de CHALLENGE — CAPTCHA/Cloudflare/"Just a moment" (Constitution §5, FR-010).

Heurísticas genéricas de challenge (não específicas da Amayama — padrões
de mercado bem documentados para Cloudflare/CAPTCHA). Nunca tenta resolver
o challenge — apenas detectar sua presença para roteamento human-in-the-loop.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from amayama_scraper.validation.detectors.base import DetectionResult

_TITLE_MARKERS = ("just a moment", "attention required", "checking your browser")
_ID_OR_CLASS_MARKERS = (
    "cf-challenge-running",
    "cf-wrapper",
    "cf-browser-verification",
    "challenge-running",
    "challenge-form",
    "g-recaptcha",
    "h-captcha",
)
_TEXT_MARKERS = (
    "verify you are human",
    "checking if the site connection is secure",
    "enable javascript and cookies to continue",
    "ray id:",
)


def detect_challenge(html: str) -> DetectionResult:
    lowered = html.lower()
    evidence: dict[str, object] = {}

    soup = BeautifulSoup(html, "lxml")
    title_text = ""
    if soup.title is not None and soup.title.string:
        title_text = soup.title.string.strip().lower()
    title_hits = [marker for marker in _TITLE_MARKERS if marker in title_text]
    if title_hits:
        evidence["title_markers"] = title_hits

    id_class_hits = [marker for marker in _ID_OR_CLASS_MARKERS if marker in lowered]
    if id_class_hits:
        evidence["id_or_class_markers"] = id_class_hits

    text_hits = [marker for marker in _TEXT_MARKERS if marker in lowered]
    if text_hits:
        evidence["text_markers"] = text_hits

    detected = bool(title_hits or id_class_hits or text_hits)
    return DetectionResult(detected=detected, evidence=evidence)
