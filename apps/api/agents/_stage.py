"""Shared stage-record helper."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any


@contextmanager
def stage(name: str, model: str | None = None):
    rec: dict[str, Any] = {
        "agent": name,
        "model": model,
        "tool_calls": [],
        "started_at": time.time(),
        "ok": True,
    }
    try:
        yield rec
    except Exception as exc:
        rec["ok"] = False
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        rec["latency_ms"] = int((time.time() - rec.pop("started_at")) * 1000)