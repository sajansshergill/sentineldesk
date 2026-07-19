"""Generator entrypoint.

    python -m data.generator.main --out ./var --n 50000

Writes:
    var/transactions.parquet   full ledger (baseline + injected anomalies)
    var/corridors.parquet      per-corridor baseline stats
    var/corpus.jsonl           email corpus for the pipeline
    data/labeled/holdout.jsonl 200-message hand-labeled extraction holdout
    var/manifest.json          seed, counts, per-class rates -- provenance

Everything is seeded. Same seed in, same bytes out.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import anomalies, config, messages, transactions


def build(seed: int = config.SEED, n: int = config.N_TRANSACTIONS,
          days: int = config.DAYS_OF_HISTORY) -> tuple[pd.DataFrame, list[dict], dict]:
    rng = np.random.default_rng(seed)

    base = transactions.generate_baseline(rng, n=n, days=days)

    injected: list[dict] = []
    counts: dict[str, int] = {}
    for spec in config.ANOMALY_SPECS:
        k = max(1, int(round(spec.base_rate * n)))
        if spec.name == "structuring":
            # base rate is per-transaction; bursts are multi-row
            k = max(1, k // 6)
        rows = anomalies.INJECTORS[spec.name](rng, base, k)
        injected.extend(rows)
        counts[spec.name] = len(rows)

    full = pd.concat([base, pd.DataFrame(injected)], ignore_index=True)
    full = full.sort_values("booked_at").reset_index(drop=True)

    corridors = transactions.corridor_baselines(full)
    corpus = messages.build_corpus(rng, full, n_messages=min(4000, len(full)))

    manifest = {
        "seed": seed,
        "n_baseline": int(len(base)),
        "n_injected": int(len(injected)),
        "n_total": int(len(full)),
        "days_of_history": days,
        "anomaly_counts": counts,
        "anomaly_rate": round(float(full["is_anomaly"].mean()), 5),
        "n_corridors": int(len(corridors)),
        "n_messages": len(corpus),
        "generator_version": "1.0.0",
        "note": "All data synthetic. Institutions are fictional.",
    }
    return full, corpus, manifest, corridors


def main() -> None:
    ap = argparse.ArgumentParser(description="SentinelDesk synthetic data generator")
    ap.add_argument("--out", default="./var", type=Path)
    ap.add_argument("--seed", default=config.SEED, type=int)
    ap.add_argument("--n", default=config.N_TRANSACTIONS, type=int)
    ap.add_argument("--days", default=config.DAYS_OF_HISTORY, type=int)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    full, corpus, manifest, corridors = build(args.seed, args.n, args.days)

    full.to_parquet(args.out / "transactions.parquet", index=False)
    corridors.to_parquet(args.out / "corridors.parquet", index=False)
    messages.write_jsonl(corpus, args.out / "corpus.jsonl")

    holdout_dir = Path("data/labeled")
    holdout_dir.mkdir(parents=True, exist_ok=True)
    messages.write_jsonl(corpus[: config.N_LABELED_HOLDOUT], holdout_dir / "holdout.jsonl")

    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(json.dumps(manifest, indent=2))
    print(f"\nwrote -> {args.out}/transactions.parquet ({len(full):,} rows)")
    print(f"wrote -> {args.out}/corpus.jsonl ({len(corpus):,} messages)")
    print(f"wrote -> data/labeled/holdout.jsonl ({config.N_LABELED_HOLDOUT} messages)")