"""Scores the AI on 10 contracts and 15 client messages. Uses the real Claude API.

Run from the backend folder (needs ANTHROPIC_API_KEY in .env):
    .venv/bin/python evals/run_evals.py              # everything
    .venv/bin/python evals/run_evals.py contracts    # contracts only
    .venv/bin/python evals/run_evals.py messages     # messages only
Only quote the scores this prints, never invented ones.
"""
import json
import mimetypes
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.ai.contract import get_contract_ai  # noqa: E402
from app.ai.guardrails import check_analysis  # noqa: E402
from app.ai.messages import check_message_analysis, get_message_ai  # noqa: E402

HOURLY_RATE = Decimal("40")


def run_contract(case: dict) -> tuple[list[str], bool]:
    """Returns (failed checks, skipped)."""
    path = HERE / case["file"]
    if not path.exists():
        return [f"missing file {case['file']}"], True
    ai = get_contract_ai()
    if path.suffix == ".txt":
        text = path.read_text()
        analysis = ai.analyse(text=text, file_bytes=None, media_type=None)
    else:
        media = mimetypes.guess_type(path.name)[0]
        analysis = ai.analyse(text=None, file_bytes=path.read_bytes(), media_type=media)
        text = analysis.transcription
    checked = check_analysis(analysis, text)

    failed = []
    if checked.currency != case["currency"]:
        failed.append(f"currency {checked.currency} != {case['currency']}")
    if case.get("milestone_amounts") is not None:
        got = [float(m.amount) for m in checked.milestones]
        if got != [float(a) for a in case["milestone_amounts"]]:
            failed.append(f"amounts {got} != {case['milestone_amounts']}")
    if case.get("stated_total") is not None and (
        checked.stated_total is None or float(checked.stated_total) != float(case["stated_total"])
    ):
        failed.append(f"total {checked.stated_total} != {case['stated_total']}")
    categories = {r.category for r in checked.risks}
    missing = [c for c in case["risks_must_include"] if c not in categories]
    if missing:
        failed.append(f"missed risks {missing}")
    if "max_risks" in case and len(checked.risks) > case["max_risks"]:
        failed.append(f"{len(checked.risks)} risks flagged on a clean contract")
    if checked.deposit_pct not in case["deposit_in"]:
        failed.append(f"deposit {checked.deposit_pct} not in {case['deposit_in']}")
    mismatch = any("add up" in w for w in checked.warnings)
    if mismatch != case["total_mismatch"]:
        failed.append(f"total mismatch flagged={mismatch}, expected {case['total_mismatch']}")
    if "triggers" in case and [m.trigger for m in checked.milestones] != case["triggers"]:
        failed.append(f"triggers {[m.trigger for m in checked.milestones]} != {case['triggers']}")
    if len(checked.ambiguities) < case.get("min_ambiguities", 0):
        failed.append(f"only {len(checked.ambiguities)} ambiguities flagged")
    return failed, False


def run_message(case: dict, data: dict) -> list[str]:
    titles = [m["title"] for m in data["milestones"]]
    analysis = get_message_ai().analyse(
        message=case["body"], contract_text=data["contract_text"], milestones=data["milestones"]
    )
    checked = check_message_analysis(analysis, case["body"], data["contract_text"], titles, HOURLY_RATE)
    failed = []
    reached = sorted(s.milestone_title for s in checked.milestone_signals)
    if reached != sorted(case["reached"]):
        failed.append(f"reached {reached} != {case['reached']}")
    if bool(checked.out_of_scope) != case["out_of_scope"]:
        failed.append(f"out_of_scope={bool(checked.out_of_scope)}, expected {case['out_of_scope']}")
    if bool(checked.revision_requests) != case["revision"]:
        failed.append(f"revision={bool(checked.revision_requests)}, expected {case['revision']}")
    return failed


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    totals = {}

    if which in ("all", "contracts"):
        cases = json.loads((HERE / "contracts.json").read_text())
        passed = ran = 0
        print("CONTRACTS")
        for case in cases:
            failed, skipped = run_contract(case)
            if skipped:
                print(f"  SKIP {case['id']} ({case['kind']}): {failed[0]}")
                continue
            ran += 1
            passed += not failed
            print(f"  {'PASS' if not failed else 'FAIL'} {case['id']} ({case['kind']})" + "".join(f"\n       - {f}" for f in failed))
        totals["contracts"] = (passed, ran)

    if which in ("all", "messages"):
        data = json.loads((HERE / "messages.json").read_text())
        passed = 0
        print("MESSAGES")
        for case in data["cases"]:
            failed = run_message(case, data)
            passed += not failed
            print(f"  {'PASS' if not failed else 'FAIL'} {case['id']} ({case['kind']})" + "".join(f"\n       - {f}" for f in failed))
        totals["messages"] = (passed, len(data["cases"]))

    print()
    for name, (passed, ran) in totals.items():
        print(f"{name}: {passed} of {ran} correct")


if __name__ == "__main__":
    main()
