"""Train and persist the anomaly model.

    python -m services.anomaly.train --data ./var --out ./var/model/iforest.joblib

Unsupervised fit. Labels are never passed in. If you find yourself wanting
to pass labels here, you want a different project.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from data.generator.config import BY_BIC
from .model import save, train


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./var", type=Path)
    ap.add_argument("--out", default="./var/model/iforest.joblib", type=Path)
    ap.add_argument("--contamination", default=0.03, type=float)
    args = ap.parse_args()

    df = pd.read_parquet(args.data / "transactions.parquet")
    corridors = pd.read_parquet(args.data / "corridors.parquet")

    fit_cols = [c for c in df.columns if c not in ("is_anomaly", "anomaly_class")]
    bundle = train(df[fit_cols], corridors, BY_BIC, contamination=args.contamination)
    save(bundle, args.out)

    print(json.dumps({
        "trained_on": int(len(df)),
        "features": bundle.feature_names,
        "contamination": args.contamination,
        "version": bundle.version,
        "out": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()