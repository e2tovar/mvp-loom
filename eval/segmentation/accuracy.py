"""Runner de exactitud de segmentación — proto-eval de M0 (SC-001/002/003).

Compara la segmentación producida por el pipeline contra las anotaciones de referencia
(`eval/fixtures/*.annotation.json`) y agrega métricas. Es la base del gate de CI
(tests/eval/test_segmentation_accuracy.py).

Formato de anotación:
    {
      "source_file": "<archivo en eval/fixtures>",
      "format": "txt|epub|docx",
      "expected_chapter_count": <int>,
      "expected_scene_separators": <int>
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.ingest.pipeline import parse_manuscript

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@dataclass
class FixtureResult:
    source_file: str
    expected_chapters: int
    detected_chapters: int
    expected_separators: int
    detected_separators: int

    @property
    def chapters_in_order(self) -> bool:
        return self.detected_chapters >= 1

    @property
    def chapter_accuracy(self) -> float:
        if self.expected_chapters == 0:
            return 1.0 if self.detected_chapters == 0 else 0.0
        diff = abs(self.detected_chapters - self.expected_chapters)
        return max(0.0, 1.0 - diff / self.expected_chapters)

    @property
    def separator_accuracy(self) -> float:
        if self.expected_separators == 0:
            return 1.0 if self.detected_separators == 0 else 0.0
        diff = abs(self.detected_separators - self.expected_separators)
        return max(0.0, 1.0 - diff / self.expected_separators)


def _detected_separators(manuscript) -> int:  # noqa: ANN001
    return sum(
        1
        for c in manuscript.chapters
        for s in c.scenes
        if s.boundary_reason == "separator"
    )


def evaluate_fixture(annotation_path: Path) -> FixtureResult:
    ann = json.loads(annotation_path.read_text(encoding="utf-8"))
    source = FIXTURES_DIR / ann["source_file"]
    manuscript = parse_manuscript(source, ann["format"])
    return FixtureResult(
        source_file=ann["source_file"],
        expected_chapters=ann["expected_chapter_count"],
        detected_chapters=manuscript.chapter_count,
        expected_separators=ann["expected_scene_separators"],
        detected_separators=_detected_separators(manuscript),
    )


def run() -> dict:
    """Evalúa todas las fixtures anotadas y agrega métricas."""
    results = [evaluate_fixture(p) for p in sorted(FIXTURES_DIR.glob("*.annotation.json"))]
    if not results:
        raise RuntimeError("No se encontraron anotaciones en eval/fixtures/*.annotation.json")

    chapter_acc = sum(r.chapter_accuracy for r in results) / len(results)
    separator_acc = sum(r.separator_accuracy for r in results) / len(results)
    return {
        "chapter_accuracy": chapter_acc,
        "separator_accuracy": separator_acc,
        "fixtures": [
            {
                "source_file": r.source_file,
                "expected_chapters": r.expected_chapters,
                "detected_chapters": r.detected_chapters,
                "chapter_accuracy": round(r.chapter_accuracy, 4),
                "expected_separators": r.expected_separators,
                "detected_separators": r.detected_separators,
                "separator_accuracy": round(r.separator_accuracy, 4),
            }
            for r in results
        ],
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2, ensure_ascii=False))
