"""Run lightweight local evals and write `evals/results/latest.md`."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from apps.api.bootstrap import create_app_state
from apps.api.llm import LocalLLMClient
from apps.api.mapper import graph_snapshot_to_run
from data.generator import config
from services.anomaly.model import load as load_model
from services.anomaly.model import save as save_model
from services.anomaly.model import train as train_model
from services.anomaly.scorer import Scorer
from services.ledger.store import Ledger


FIELDS = ["reference", "sender_bic", "receiver_bic", "currency", "amount", "value_date", "message_type"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="./var", type=Path)
    args = parser.parse_args()

    os.environ["SENTINEL_DATA_DIR"] = str(args.data)
    state = create_app_state()
    extraction = extraction_eval(state.data_dir)
    anomaly = anomaly_eval(state.data_dir)
    trajectory = trajectory_eval(state)
    citations = citation_eval(state)

    results = {
        "extraction": extraction,
        "anomaly": anomaly,
        "trajectory": trajectory,
        "citations": citations,
    }
    out = Path("evals/results/latest.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(results), encoding="utf-8")
    print(json.dumps(results, indent=2))


def extraction_eval(data_dir: Path) -> dict[str, Any]:
    holdout = Path("data/labeled/holdout.jsonl")
    records = list(_read_jsonl(holdout if holdout.exists() else data_dir / "corpus.jsonl"))[:100]
    llm = LocalLLMClient()
    total = 0
    correct = 0
    for record in records:
        email = record["email"]
        truth = record["truth"]
        prompt = _extract_prompt(email)
        prediction = llm.complete("EXTRACTION_TASK", prompt).json()
        for field in FIELDS:
            total += 1
            actual = prediction.get(field)
            expected = truth.get(field)
            if field == "amount":
                ok = abs(float(actual or 0) - float(expected or 0)) < 0.01
            else:
                ok = str(actual) == str(expected)
            correct += int(ok)
    return {
        "messages": len(records),
        "field_accuracy": round(correct / max(total, 1), 4),
        "fields_checked": total,
    }


def anomaly_eval(data_dir: Path) -> dict[str, Any]:
    df = pd.read_parquet(data_dir / "transactions.parquet")
    corridors = pd.read_parquet(data_dir / "corridors.parquet")
    ledger = Ledger(":memory:")
    ledger.load_frame(df)
    model_path = data_dir / "model" / "iforest.joblib"
    if model_path.exists():
        bundle = load_model(model_path)
    else:
        fit_cols = [col for col in df.columns if col not in ("is_anomaly", "anomaly_class")]
        bundle = train_model(df[fit_cols], corridors, config.BY_BIC)
        save_model(bundle, model_path)
    scored = Scorer(bundle, corridors, config.BY_BIC, ledger).score_frame(df)
    truth = df["is_anomaly"].astype(bool)
    pred = scored["alerts"].astype(bool)
    tp = int((truth & pred).sum())
    fp = int((~truth & pred).sum())
    fn = int((truth & ~pred).sum())
    return {
        "rows": int(len(df)),
        "precision": round(tp / max(tp + fp, 1), 4),
        "recall": round(tp / max(tp + fn, 1), 4),
        "alerts": int(pred.sum()),
    }


def trajectory_eval(state) -> dict[str, Any]:
    snapshots = state.snapshots()
    runs = [graph_snapshot_to_run(snapshot, crm=state.crm) for snapshot in snapshots]
    pending = sum(1 for run in runs if run["status"] == "pending_approval")
    halted = sum(1 for run in runs if run["status"] == "halted")
    return {
        "runs": len(runs),
        "pending_approval": pending,
        "halted": halted,
        "success_rate": round(pending / max(len(runs), 1), 4),
    }


def citation_eval(state) -> dict[str, Any]:
    total = 0
    valid = 0
    for snapshot in state.snapshots():
        values = snapshot.get("values") or {}
        allowed = set(values.get("evidence_ids") or [])
        for citation in (values.get("brief") or {}).get("citations", []):
            total += 1
            valid += int(citation.get("ref") in allowed)
    return {"citations": total, "valid_rate": round(valid / max(total, 1), 4)}


def render_markdown(results: dict[str, Any]) -> str:
    lines = [
        "# SentinelDesk Local Eval Results",
        "",
        "These metrics are generated from synthetic data and local stubs. They are engineering regression checks, not production compliance claims.",
        "",
        "## Summary",
        "",
        f"- Extraction field accuracy: {results['extraction']['field_accuracy']:.2%} over {results['extraction']['fields_checked']} fields.",
        f"- Anomaly precision/recall: {results['anomaly']['precision']:.2%} / {results['anomaly']['recall']:.2%}.",
        f"- Trajectory success rate: {results['trajectory']['success_rate']:.2%}.",
        f"- Citation valid rate: {results['citations']['valid_rate']:.2%}.",
        "",
        "## Raw JSON",
        "",
        "```json",
        json.dumps(results, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def _extract_prompt(email: dict[str, Any]) -> str:
    attachment = "\n".join(item.get("content", "") for item in email.get("attachments", []))
    parts = [
        f"Subject: {email.get('subject', '')}",
        f"From: {email.get('from', '')}",
        "",
        "<<<BODY>>>",
        email.get("body", ""),
        "<<<END_BODY>>>",
    ]
    if attachment.strip():
        parts.extend(["", "<<<ATTACHMENT>>>", attachment, "<<<END_ATTACHMENT>>>"])
    return "\n".join(parts)


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


if __name__ == "__main__":
    main()
