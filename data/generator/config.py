"""Generator configuration.

All data produced by this package is SYNTHETIC. Institution names are
fictional and do not correspond to real central banks. Base rates are chosen
to be plausible-ish for a surveillance workload, not to model reality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEED = 20260715

N_TRANSACTIONS = 50_000
DAYS_OF_HISTORY = 365

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "SEK"]


@dataclass(frozen=True)
class Institution:
    """A fictional counterparty institution."""

    bic: str
    name: str
    country: str
    tz_offset: int          # hours from UTC; drives the operating window
    base_currency: str
    daily_volume: float     # mean transactions per day
    mean_amount: float      # lognormal location for amount, in base currency
    open_hour: int = 8      # local operating window start
    close_hour: int = 17    # local operating window end


INSTITUTIONS: list[Institution] = [
    Institution("ZKBNARTA", "Reserve Bank of Artavia", "AR", -3, "USD", 42.0, 480_000, 9, 17),
    Institution("BRVLBRXX", "Banco Central de Brivela", "BV", -4, "USD", 31.0, 350_000, 8, 16),
    Institution("CNTLCLDN", "Caledon Monetary Authority", "CL", 0, "GBP", 55.0, 620_000, 8, 17),
    Institution("DRMSDMXX", "Dromund National Bank", "DM", 1, "EUR", 61.0, 710_000, 8, 18),
    Institution("ESVRESXX", "Central Bank of Esveria", "ES", 2, "EUR", 38.0, 410_000, 9, 17),
    Institution("FJORFJXX", "Fjordane Riksbank", "FJ", 1, "SEK", 27.0, 300_000, 8, 16),
    Institution("GLNTGLXX", "Bank of Glantri", "GL", 3, "EUR", 22.0, 265_000, 9, 18),
    Institution("HVNSHVXX", "Havenshire Reserve", "HV", 0, "GBP", 47.0, 540_000, 8, 17),
    Institution("IRVNIRXX", "Irvane Monetary Board", "IR", 4, "USD", 18.0, 220_000, 9, 17),
    Institution("JOTNJTXX", "Jotunheim Central Bank", "JT", 2, "EUR", 25.0, 280_000, 8, 16),
    Institution("KRSNKRXX", "Korsun State Bank", "KR", 5, "USD", 15.0, 195_000, 9, 18),
    Institution("LMBRLMXX", "Lombard Reserve Authority", "LM", 1, "CHF", 44.0, 505_000, 8, 17),
    Institution("MRDNMRXX", "Meridian Central Bank", "MR", -5, "CAD", 36.0, 395_000, 9, 17),
    Institution("NVSKNVXX", "Novask National Reserve", "NV", 6, "USD", 12.0, 175_000, 9, 18),
    Institution("ORLNORXX", "Orlaine Banque Centrale", "OR", 1, "EUR", 52.0, 590_000, 8, 18),
    Institution("PRTHPRXX", "Porthaven Monetary Authority", "PR", 8, "AUD", 29.0, 320_000, 9, 17),
    Institution("QRNSQRXX", "Quarnos Reserve Bank", "QR", 9, "JPY", 33.0, 40_000_000, 9, 17),
    Institution("RVNSRVXX", "Ravensmoor Central Bank", "RV", 0, "GBP", 40.0, 460_000, 8, 17),
    Institution("STRLSTXX", "Sterling Bay Reserve", "ST", -6, "USD", 49.0, 560_000, 9, 17),
    Institution("TRVSTRXX", "Travance National Bank", "TR", 7, "JPY", 21.0, 26_000_000, 9, 18),
]

BY_BIC = {i.bic: i for i in INSTITUTIONS}

# Corridors that exist in the baseline. Anything outside this set is "novel".
# Built at import time as a dense-ish but not complete graph.
ESTABLISHED_CORRIDORS: set[tuple[str, str]] = set()


def _build_corridors() -> None:
    bics = [i.bic for i in INSTITUTIONS]
    for idx, a in enumerate(bics):
        # each institution trades with a deterministic slice of the others
        partners = bics[idx + 1: idx + 8] + bics[max(0, idx - 3): idx]
        for b in partners:
            if a != b:
                ESTABLISHED_CORRIDORS.add((a, b))


_build_corridors()


@dataclass(frozen=True)
class AnomalySpec:
    """One injected anomaly class."""

    name: str
    base_rate: float
    detectable_by: str  # "rules" | "model" | "both"
    description: str


ANOMALY_SPECS: list[AnomalySpec] = [
    AnomalySpec(
        "duplicate_settlement", 0.004, "rules",
        "Same instruction resent with a near-identical reference within 48h.",
    ),
    AnomalySpec(
        "amount_transposition", 0.003, "both",
        "Two adjacent digits swapped versus the confirming message.",
    ),
    AnomalySpec(
        "novel_corridor", 0.006, "rules",
        "First-ever settlement between an institution pair.",
    ),
    AnomalySpec(
        "off_cycle_timing", 0.005, "model",
        "Settlement booked outside the corridor's historical operating window.",
    ),
    AnomalySpec(
        "structuring", 0.002, "rules",
        "Burst of transactions individually below a reporting threshold.",
    ),
    AnomalySpec(
        "drift", 0.010, "model",
        "Unlabeled distributional drift: amount and timing jointly off-baseline.",
    ),
]

STRUCTURING_THRESHOLD = 10_000.0  # reporting threshold the pattern hides under

# Message corpus
N_LABELED_HOLDOUT = 200
ATTACHMENT_RATE = 0.35   # fraction of emails carrying an MT-style attachment
NOISE_RATE = 0.15        # fraction with forwarded chains / signatures / disclaimers