"""Email + MT-style message corpus.

Each transaction can produce an inbound email carrying a settlement
instruction or confirmation. The email is what the extraction agent sees;
the transaction row is the ground truth it is scored against.

Realism levers that matter for extraction difficulty:
  - free-text bodies vs. structured MT blocks in an attachment
  - forwarded chains, signatures, legal disclaimers (distractor amounts/dates)
  - inconsistent date formats
  - amounts written with thousands separators, currency before or after
"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from .config import ATTACHMENT_RATE, BY_BIC, NOISE_RATE

DISCLAIMER = (
    "This message and any attachments are confidential and intended solely for "
    "the addressee. If you have received this in error please notify the sender "
    "and delete it. Reference 99999999 is not a settlement reference."
)

SIGNATURE_TMPL = """--
{name}
Settlement Operations | {inst}
Direct: +00 000 0000 | Desk ref 4471234
"""

FORWARD_TMPL = """
-----Original Message-----
From: ops.desk@{dom}.example
Sent: {sent}
Subject: RE: Prior settlement batch 8829301
Please disregard the earlier batch total of 1,250,000.00 quoted below.
"""


def _fmt_amount(rng, amount: float, currency: str) -> str:
    style = rng.random()
    if style < 0.45:
        return f"{currency} {amount:,.2f}"
    if style < 0.8:
        return f"{amount:,.2f} {currency}"
    return f"{currency}{amount:.2f}"


def _fmt_date(rng, iso: str) -> str:
    d = datetime.fromisoformat(iso) if "T" in iso else datetime.fromisoformat(iso + "T00:00:00")
    style = rng.random()
    if style < 0.4:
        return d.strftime("%d %B %Y")
    if style < 0.7:
        return d.strftime("%Y-%m-%d")
    if style < 0.9:
        return d.strftime("%d/%m/%Y")
    return d.strftime("%d-%b-%y").upper()


def mt_block(txn: dict) -> str:
    """MT103/MT202-shaped attachment body.

    Field tags follow the public message structure closely enough to be
    recognisable; this is a teaching artifact, not a certified formatter.
    """
    d = datetime.fromisoformat(txn["value_date"] + "T00:00:00") \
        if "T" not in txn["value_date"] else datetime.fromisoformat(txn["value_date"])
    vd = d.strftime("%y%m%d")
    amt = f"{txn['amount']:.2f}".replace(".", ",")
    tag32 = f":32A:{vd}{txn['currency']}{amt}"
    if txn["message_type"] == "MT202":
        return "\n".join([
            "{1:F01" + txn["sender_bic"] + "0000000000}",
            "{2:I202" + txn["receiver_bic"] + "N}",
            "{4:",
            f":20:{txn['reference']}",
            f":21:{txn['reference'][::-1][:16]}",
            tag32,
            f":52A:{txn['sender_bic']}",
            f":58A:{txn['receiver_bic']}",
            "-}",
        ])
    return "\n".join([
        "{1:F01" + txn["sender_bic"] + "0000000000}",
        "{2:I103" + txn["receiver_bic"] + "N}",
        "{4:",
        f":20:{txn['reference']}",
        ":23B:CRED",
        tag32,
        f":50K:/{txn['sender_bic']}\n{BY_BIC[txn['sender_bic']].name}",
        f":59:/{txn['receiver_bic']}\n{BY_BIC[txn['receiver_bic']].name}",
        ":71A:SHA",
        "-}",
    ])


def email_body(rng, txn: dict, has_attachment: bool, noisy: bool) -> str:
    sender = BY_BIC[txn["sender_bic"]]
    receiver = BY_BIC[txn["receiver_bic"]]
    amt = _fmt_amount(rng, txn["amount"], txn["currency"])
    vd = _fmt_date(rng, txn["value_date"])
    kind = "confirmation" if rng.random() < 0.5 else "instruction"

    parts = [f"Dear Colleagues,", ""]
    if has_attachment:
        parts += [
            f"Please find attached the {txn['message_type']} {kind} for value {vd}.",
            f"Our reference is {txn['reference']}.",
            "",
            "Kindly acknowledge receipt.",
        ]
    else:
        parts += [
            f"We {'confirm' if kind == 'confirmation' else 'instruct'} settlement of {amt} "
            f"for value {vd}.",
            f"Ordering institution: {sender.name} ({txn['sender_bic']})",
            f"Beneficiary institution: {receiver.name} ({txn['receiver_bic']})",
            f"Our reference: {txn['reference']}",
            f"Message type: {txn['message_type']}",
        ]
    parts += ["", "Regards,"]
    parts.append(SIGNATURE_TMPL.format(
        name=str(rng.choice(["A. Marsh", "J. Okonkwo", "L. Bergström", "R. Whitlock",
                             "S. Nakamura", "T. Aliyev", "M. Duarte"])),
        inst=sender.name,
    ))
    if noisy:
        parts.append(FORWARD_TMPL.format(
            dom=sender.bic[:4].lower(),
            sent=_fmt_date(rng, txn["booked_at"]),
        ))
    parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts)


def build_corpus(rng: np.random.Generator, df: pd.DataFrame,
                 n_messages: int) -> list[dict]:
    """Build `n_messages` emails sampled from the transaction frame.

    Returns records with `email` (what the agent sees) and `truth`
    (what it should have extracted).
    """
    picks = rng.choice(len(df), size=min(n_messages, len(df)), replace=False)
    corpus = []
    for i, idx in enumerate(picks):
        txn = df.iloc[idx].to_dict()
        has_attachment = bool(rng.random() < ATTACHMENT_RATE)
        noisy = bool(rng.random() < NOISE_RATE)

        record = {
            "message_id": f"msg-{i:05d}",
            "email": {
                "from": f"settlements@{txn['sender_bic'][:4].lower()}.example",
                "to": "correspondent.ops@sentineldesk.example",
                "subject": f"{txn['message_type']} {txn['reference']} "
                           f"value {_fmt_date(rng, txn['value_date'])}",
                "received_at": txn["booked_at"],
                "body": email_body(rng, txn, has_attachment, noisy),
                "attachments": (
                    [{"filename": f"{txn['reference']}.txt",
                      "content_type": "text/plain",
                      "content": mt_block(txn)}]
                    if has_attachment else []
                ),
            },
            "truth": {
                "reference": txn["reference"],
                "sender_bic": txn["sender_bic"],
                "receiver_bic": txn["receiver_bic"],
                "currency": txn["currency"],
                "amount": float(txn["amount"]),
                "value_date": txn["value_date"],
                "message_type": txn["message_type"],
            },
            "meta": {
                "txn_id": txn["txn_id"],
                "has_attachment": has_attachment,
                "noisy": noisy,
                "is_anomaly": bool(txn["is_anomaly"]),
                "anomaly_class": txn["anomaly_class"],
            },
        }
        corpus.append(record)
    return corpus


def write_jsonl(records: list[dict], path) -> None:
    with open(path, "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")