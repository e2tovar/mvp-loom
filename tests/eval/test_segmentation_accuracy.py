"""Gate del proto-eval de segmentación (T029, Principio I).

Bloquea el merge si la exactitud de capítulos (SC-002) o de separadores de escena
(SC-003) cae bajo umbral.
"""

from __future__ import annotations

import pytest

from eval.segmentation.accuracy import run

pytestmark = pytest.mark.eval

CHAPTER_THRESHOLD = 0.95  # SC-002
SEPARATOR_THRESHOLD = 0.90  # SC-003


def test_segmentation_accuracy_meets_thresholds():
    report = run()
    assert report["chapter_accuracy"] >= CHAPTER_THRESHOLD, report
    assert report["separator_accuracy"] >= SEPARATOR_THRESHOLD, report


def test_every_fixture_detects_all_chapters_in_order():
    # SC-001: el 100% de los capítulos aparece (exactitud perfecta por fixture).
    report = run()
    for fx in report["fixtures"]:
        assert fx["detected_chapters"] == fx["expected_chapters"], fx
