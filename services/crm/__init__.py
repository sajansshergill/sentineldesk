"""CRM sinks. MODE=local -> StubCRM; otherwise DataverseCRM."""

from __future__ import annotations

import os

from .stub import StubCRM


def get_crm():
    if os.getenv("MODE", "local").lower() == "local":
        return StubCRM()
    from .dataverse import DataverseCRM

    return DataverseCRM()


__all__ = ["StubCRM", "get_crm"]