"""Detector de INCOMPLETE — captura estruturalmente válida, porém parcial (FR-010).

Heurística genérica de truncamento: verifica ausência das tags de
fechamento esperadas no texto bruto (não na árvore já reparada pelo
parser tolerante, que mascararia o truncamento).
"""

from __future__ import annotations

from amayama_scraper.validation.detectors.base import DetectionResult


def detect_incomplete(html: str) -> DetectionResult:
    lowered = html.strip().lower()
    missing: list[str] = []

    if "<html" in lowered and "</html>" not in lowered:
        missing.append("</html>")
    if "<body" in lowered and "</body>" not in lowered:
        missing.append("</body>")

    detected = bool(missing)
    evidence: dict[str, object] = {"missing_closing_tags": missing} if detected else {}
    return DetectionResult(detected=detected, evidence=evidence)
