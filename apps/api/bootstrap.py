"""Local application bootstrap."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from data.generator import config
from data.generator.main import build as build_data
from services.anomaly.model import load as load_model
from services.anomaly.model import save as save_model
from services.anomaly.model import train as train_model
from services.anomaly.scorer import Scorer
from services.crm import get_crm
from services.ledger.store import Ledger

from .graph import build_graph, get_run, resume_run, start_run
from .llm import LocalLLMClient
from .mapper import graph_snapshot_to_run


@dataclass
class AppState:
    mode: str
    data_dir: Path
    ledger: Ledger
    scorer: Scorer
    crm: Any
    llm: LocalLLMClient
    graph: Any
    run_ids: list[str] = field(default_factory=list)

    def snapshots(self) -> list[dict[str, Any]]:
        return [get_run(self.graph, run_id) for run_id in self.run_ids]


def create_app_state() -> AppState:
    mode = os.getenv("MODE", "local").lower()
    data_dir = Path(os.getenv("SENTINEL_DATA_DIR", "./var"))
    data_dir.mkdir(parents=True, exist_ok=True)
    _ensure_data(data_dir)

    transactions = pd.read_parquet(data_dir / "transactions.parquet")
    corridors = pd.read_parquet(data_dir / "corridors.parquet")
    ledger = Ledger(os.getenv("SENTINEL_LEDGER_PATH", ":memory:"))
    ledger.load_frame(_ledger_columns(transactions))

    model_path = data_dir / "model" / "iforest.joblib"
    if model_path.exists():
        bundle = load_model(model_path)
    else:
        fit_cols = [col for col in transactions.columns if col not in ("is_anomaly", "anomaly_class")]
        bundle = train_model(transactions[fit_cols], corridors, config.BY_BIC)
        save_model(bundle, model_path)

    scorer = Scorer(bundle, corridors, config.BY_BIC, ledger)
    crm = get_crm()
    llm = LocalLLMClient()
    compiled_graph = build_graph(llm=llm, ledger=ledger, scorer=scorer, crm=crm)
    state = AppState(mode=mode, data_dir=data_dir, ledger=ledger, scorer=scorer, crm=crm, llm=llm, graph=compiled_graph)
    _seed_runs(state)
    return state


def start_email_run(state: AppState, email: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
    rid, _ = start_run(state.graph, email, run_id=run_id)
    if rid not in state.run_ids:
        state.run_ids.insert(0, rid)
    return graph_snapshot_to_run(get_run(state.graph, rid), crm=state.crm)


def decide_run(state: AppState, run_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    resume_run(state.graph, run_id, decision)
    return graph_snapshot_to_run(get_run(state.graph, run_id), crm=state.crm)


def _ensure_data(data_dir: Path) -> None:
    required = [data_dir / "transactions.parquet", data_dir / "corridors.parquet", data_dir / "corpus.jsonl"]
    if all(path.exists() for path in required):
        return
    n = int(os.getenv("SENTINEL_DATA_N", "2500"))
    full, corpus, manifest, corridors = build_data(n=n)
    full.to_parquet(data_dir / "transactions.parquet", index=False)
    corridors.to_parquet(data_dir / "corridors.parquet", index=False)
    _write_jsonl(corpus, data_dir / "corpus.jsonl")
    labeled = Path("data/labeled")
    labeled.mkdir(parents=True, exist_ok=True)
    _write_jsonl(corpus[: config.N_LABELED_HOLDOUT], labeled / "holdout.jsonl")
    (data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _seed_runs(state: AppState) -> None:
    corpus_path = state.data_dir / "corpus.jsonl"
    if not corpus_path.exists():
        return
    for idx, record in enumerate(_read_jsonl(corpus_path)):
        if idx >= int(os.getenv("SENTINEL_SEED_RUNS", "3")):
            break
        start_email_run(state, record["email"], run_id=f"seed-{record['message_id']}")


def _ledger_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
            "txn_id",
            "reference",
            "sender_bic",
            "receiver_bic",
            "currency",
            "amount",
            "amount_usd",
            "value_date",
            "booked_at",
            "message_type",
            "is_anomaly",
            "anomaly_class",
        ]
    ].copy()


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)
