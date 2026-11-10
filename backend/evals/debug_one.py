"""Reads one eval contract with the real AI and prints its raw answer. One AI call.

Run from the backend folder:  .venv/bin/python evals/debug_one.py c02
"""
import json
import mimetypes
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.ai.contract import get_contract_ai  # noqa: E402
from app.ai.guardrails import check_analysis  # noqa: E402
from app.db import init_db  # noqa: E402

init_db()
case = next(c for c in json.loads((HERE / "contracts.json").read_text()) if c["id"] == sys.argv[1])
path = HERE / case["file"]
if path.suffix == ".txt":
    text = path.read_text()
    analysis = get_contract_ai().analyse(text=text, file_bytes=None, media_type=None)
else:
    analysis = get_contract_ai().analyse(text=None, file_bytes=path.read_bytes(), media_type=mimetypes.guess_type(path.name)[0])
    text = analysis.transcription
print("RAW AI ANSWER")
print(analysis.model_dump_json(indent=2))
print("\nCODE CHECK WARNINGS")
for w in check_analysis(analysis, text).warnings:
    print(" -", w)
