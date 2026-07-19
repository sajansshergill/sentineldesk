"""Isolation Forest wrapper.

Trained unsupervised on the full ledger (we do not get labels in production).
The injected labels are used ONLY at eval time to score the detector -- never
to fit it. Keeping that boundary honest is the whole point; a supervised model
trained on my own injected classes would score beautifully and mean nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_NAMES, build_features


@dataclass
class ModelBundle:
    scaler: StandardScaler
    forest: IsolationForest
    feature_names: list[str]
    version: str

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Return anomaly score in [0, 1]; higher = more anomalous."""
        Xs = self.scaler.transform(X[self.feature_names])
        raw = -self.forest.score_samples(Xs)   # higher = more anomalous
        lo, hi = self._calib
        return np.clip((raw - lo) / (hi - lo + 1e-9), 0.0, 1.0)

    def attribute(self, X: pd.DataFrame, row: int) -> dict[str, float]:
        """Cheap per-feature attribution: z-score of the feature versus the
        training distribution. Not SHAP -- honest about being a heuristic,
        but enough to tell an analyst *which* feature looks strange."""
        Xs = self.scaler.transform(X[self.feature_names])
        return {
            name: round(float(Xs[row, i]), 3)
            for i, name in enumerate(self.feature_names)
        }


def train(df: pd.DataFrame, corridors: pd.DataFrame, institutions: dict,
          contamination: float = 0.03, seed: int = 20260715) -> ModelBundle:
    X = build_features(df, corridors, institutions)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)

    forest = IsolationForest(
        n_estimators=300,
        contamination=contamination,
        max_samples=min(4096, len(Xs)),
        random_state=seed,
        n_jobs=-1,
    ).fit(Xs)

    raw = -forest.score_samples(Xs)
    bundle = ModelBundle(scaler, forest, list(FEATURE_NAMES), "iforest-1.0.0")
    bundle._calib = (float(np.percentile(raw, 1)), float(np.percentile(raw, 99)))
    return bundle


def save(bundle: ModelBundle, path: Path) -> None:
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    meta = {
        "version": bundle.version,
        "features": bundle.feature_names,
        "calibration": bundle._calib,
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))


def load(path: Path) -> ModelBundle:
    import joblib

    return joblib.load(path)