"""Write evals/RESULTS.md. Failures stay in the table."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "RESULTS.md"


def write_report(rows: list[dict], mode: str) -> Path:
    passed = sum(1 for row in rows if row["passed"])
    total = len(rows)
    lines = [
        "# Eval Lab results",
        "",
        f"Mode: {mode}.",
        "",
        "This scorecard drives the same tool implementations the phone agent uses.",
        "It does not listen to audio. Naturalness of a live call is not in these numbers.",
        "An LLM-vs-LLM run is `python -m evals.run --llm` when `EVAL_LLM_API_KEY` is set.",
        "",
        f"Pass rate: **{passed}/{total}** ({(100 * passed / total) if total else 0:.0f}%).",
        "",
        "| Scenario | Result | Turns | Notes |",
        "|---|---|---|---|",
    ]
    for row in rows:
        result = "pass" if row["passed"] else "fail"
        notes = "; ".join(row["notes"]) if row["notes"] else row["description"]
        notes = notes.replace("|", "/")
        lines.append(f"| {row['id']} | {result} | {row['turns']} | {notes} |")
    failures = [row for row in rows if not row["passed"]]
    lines.extend(["", "## Known failures", ""])
    if not failures:
        lines.append(
            "No deterministic scenario failed in this run. "
            "The open gap is conversational: this harness does not prove the live model will follow the prompt on a noisy phone call. "
            "Silence handling is a Vapi timeout (`silenceTimeoutSeconds`), checked here as configuration, not as audio."
        )
    else:
        for row in failures:
            lines.append(f"- **{row['id']}**: {'; '.join(row['notes'])}")
    lines.append("")
    RESULTS.write_text("\n".join(lines), encoding="utf-8")
    return RESULTS
