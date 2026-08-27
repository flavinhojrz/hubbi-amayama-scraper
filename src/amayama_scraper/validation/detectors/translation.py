"""Detector de TRANSLATION_CONTAMINATED — tradução automática do navegador (FR-010).

Heurísticas genéricas de marcação deixada por extensões/recursos de
tradução automática (ex.: Google Translate) no DOM.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from amayama_scraper.validation.detectors.base import DetectionResult

_HTML_CLASS_MARKERS = ("translated-ltr", "translated-rtl")
_ATTRIBUTE_MARKERS = ("_msttexthash", "goog-trans-section", "notranslate")
_META_NAME_MARKERS = ("google", "google-translate-customization")


def detect_translation_contamination(html: str) -> DetectionResult:
    soup = BeautifulSoup(html, "lxml")
    evidence: dict[str, object] = {}

    html_tag = soup.find("html")
    html_classes: list[str] = []
    if html_tag is not None:
        classes: list[str] = html_tag.get("class") or []  # type: ignore[assignment]
        html_classes = [c for c in classes if c.lower() in _HTML_CLASS_MARKERS]
    if html_classes:
        evidence["html_class_markers"] = html_classes

    lowered = html.lower()
    attribute_hits = [marker for marker in _ATTRIBUTE_MARKERS if marker.lower() in lowered]
    if attribute_hits:
        evidence["attribute_markers"] = attribute_hits

    meta_hits = [
        meta.get("content")
        for meta in soup.find_all("meta", attrs={"name": "google-translate-customization"})
    ]
    meta_hits = [m for m in meta_hits if m]
    if meta_hits:
        evidence["meta_markers"] = meta_hits

    detected = bool(html_classes or attribute_hits or meta_hits)
    return DetectionResult(detected=detected, evidence=evidence)
