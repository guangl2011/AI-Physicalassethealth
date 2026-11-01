"""The demo runbook: the D3 reviewer's end-to-end check in one command.

``make demo`` runs this module. It ingests the synthetic seed corpus through
the real HTTP routes and shows, in order:

1. the ingestion report (every row accounted for),
2. one **ranked** diagnosis with citations (source work orders and the
   evidence spans that back them),
3. one **abstention** — a thin-history asset, with its rationale and what
   would help, and no confidence figure anywhere,
4. one **feedback round-trip** — a technician verdict posted to and echoed
   back from the feedback API.

All output is derived from the synthetic seed data (see
``docs/testing-plan.md`` §0) — safe to print, commit, or paste.

Run: ``python -m evals.demo`` (or ``make demo``).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from evals.dataset import AS_OF, build_store, ingest_seed_corpus, session_factory
from insmart_api.integrity import graph_integrity_violations

# A rich asset with two adjudicated causes and no unresolved contradiction —
# it ranks. A thin-history asset with two work orders — it must abstain.
RANKED_ASSET = "RTU-4"
ABSTAINING_ASSET = "AHU-4"


def diagnose(client: TestClient, asset_id: str) -> dict[str, Any]:
    """Diagnose one asset at the pinned demo moment (deterministic output)."""
    response = client.get(f"/assets/{asset_id}/diagnosis", params={"as_of": AS_OF})
    assert response.status_code == 200, response.text
    diagnosis: dict[str, Any] = response.json()
    return diagnosis


def run_demo(client: TestClient) -> dict[str, Any]:
    """Execute the full demo flow on a fresh store and return the outputs."""
    ingest = ingest_seed_corpus(client)
    ranked = diagnose(client, RANKED_ASSET)
    abstention = diagnose(client, ABSTAINING_ASSET)
    feedback_response = client.post(
        f"/diagnoses/{ranked['diagnosis_id']}/feedback",
        json={"verdict": "confirm", "note": "Matches the most recent findings."},
    )
    assert feedback_response.status_code == 200, feedback_response.text
    feedback: dict[str, Any] = feedback_response.json()
    return {
        "ingest": ingest,
        "ranked": ranked,
        "abstention": abstention,
        "feedback": feedback,
    }


def print_demo(outputs: dict[str, Any]) -> None:
    """Render the demo flow for the reviewer."""
    ingest = outputs["ingest"]
    print("== Insmart AI demo — synthetic seed corpus ==")
    print(
        f"\n[1] Ingested {ingest['rows_ingested']} rows "
        f"({ingest['rows_deduplicated']} deduplicated, "
        f"{ingest['rows_reviewed']} sent to review) from {ingest['source_name']}."
    )

    ranked = outputs["ranked"]
    print(f"\n[2] Ranked diagnosis for {RANKED_ASSET} — state: {ranked['state']}")
    for cause in ranked["causes"]:
        print(
            f"    {cause['label']} — confidence {cause['confidence']:.2f}, "
            f"{cause['observation_count']} record(s)"
        )
        refs = ", ".join(cause["source_refs"])
        spans = ", ".join(f'"{span}"' for span in cause["evidence_spans"])
        print(f"      citations: {refs}")
        print(f"      evidence: {spans}")

    abstention = outputs["abstention"]
    print(f"\n[3] Abstention for {ABSTAINING_ASSET} — state: {abstention['state']}")
    print(f"    why: {abstention['rationale']}")
    print(f"    what would help: {abstention['what_would_help']}")

    feedback = outputs["feedback"]
    print("\n[4] Feedback round-trip on the ranked diagnosis:")
    print(f"    {json.dumps(feedback)}")
    print("\nAll output above is synthetic (seed corpus, fixed seed 42).")


def main() -> int:
    """Build a throwaway store, run the flow, verify graph integrity, print."""
    with tempfile.TemporaryDirectory() as tmp:
        client = build_store(Path(tmp) / "demo.db")
        outputs = run_demo(client)
        violations = graph_integrity_violations(session_factory(client)())
    print_demo(outputs)
    if violations:
        print(f"\nGraph integrity violations: {violations}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
