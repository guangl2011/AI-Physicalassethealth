"""CI gate for the demo runbook entry point.

The eval harness tests (``test_evals.py``) exercise the metrics but never run
``python -m evals.demo`` — which is how a stale import shipped. This smoke
test runs the exact ``make demo`` command as a subprocess and asserts it
completes with the four demo sections in its output.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Output markers, one per section of print_demo (ingest, ranked diagnosis,
# abstention, feedback round-trip).
EXPECTED_MARKERS = (
    "== Insmart AI demo",
    "[1] Ingested",
    "[2] Ranked diagnosis",
    "[3] Abstention",
    "[4] Feedback round-trip",
)


def test_demo_entry_point_runs_end_to_end() -> None:
    """`make demo` must complete: exit 0, all four demo sections printed."""
    result = subprocess.run(
        [sys.executable, "-m", "evals.demo"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for marker in EXPECTED_MARKERS:
        assert marker in result.stdout, f"missing demo section {marker!r}"
