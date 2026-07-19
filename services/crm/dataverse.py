"""Dynamics 365 / Dataverse Web API client.

Setup gotchas that cost me real time (documented in docs/enterprise-setup.md):

  - The OAuth scope is `https://<org>.crm.dynamics.com/.default`, NOT
    `.../user_impersonation`, for client-credentials flow.
  - An app registration is not enough: the service principal must also be
    created as an Application User inside the Dynamics environment and given
    a security role. Without that you get a 401 that reads like a token
    problem but is not.
  - Idempotency: Dataverse honours the `MSCRM.SuppressDuplicateDetection`
    header, but for true idempotency we use an alternate key on a custom
    field (`sd_idempotencykey`) and PATCH with upsert semantics.
"""

from __future__ import annotations

import os
import time

import requests


class DataverseCRM:
    def __init__(self, org_url: str | None = None, tenant_id: str | None = None,
                 client_id: str | None = None, client_secret: str | None = None,
                 table: str = "sd_surveillancecases") -> None:
        self.org_url = (org_url or os.environ["DATAVERSE_ORG_URL"]).rstrip("/")
        self.tenant_id = tenant_id or os.environ["AZURE_TENANT_ID"]
        self.client_id = client_id or os.environ["AZURE_CLIENT_ID"]
        self.client_secret = client_secret or os.environ["AZURE_CLIENT_SECRET"]
        self.table = table
        self._token: str | None = None
        self._token_exp: float = 0.0

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        resp = requests.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": f"{self.org_url}/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_exp = time.time() + payload.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Prefer": "return=representation",
        }

    def upsert_case(self, idempotency_key: str, **fields) -> dict:
        """Upsert by alternate key. Safe to call twice with the same key."""
        body = {
            "sd_idempotencykey": idempotency_key,
            "sd_reference": fields.get("reference"),
            "sd_score": fields.get("score"),
            "sd_headline": fields.get("headline"),
            "sd_summary": fields.get("summary"),
            "sd_recommendedaction": fields.get("recommended_action"),
            "sd_decision": fields.get("decision"),
            "sd_actor": fields.get("actor"),
        }
        body = {k: v for k, v in body.items() if v is not None}

        url = (f"{self.org_url}/api/data/v9.2/{self.table}"
               f"(sd_idempotencykey='{idempotency_key}')")
        resp = requests.patch(url, json=body, headers=self._headers(), timeout=30)
        if resp.status_code in (200, 201, 204):
            data = resp.json() if resp.content else {}
            return {
                "record_id": data.get(f"{self.table[:-1]}id") or idempotency_key,
                "status": "created" if resp.status_code == 201 else "updated",
                "deduped": resp.status_code == 200,
                "url": f"{self.org_url}/main.aspx?etn={self.table[:-1]}"
                       f"&id={data.get(f'{self.table[:-1]}id', '')}&pagetype=entityrecord",
            }
        resp.raise_for_status()
        return {"status": "unknown", "code": resp.status_code}

    def get_case(self, idempotency_key: str) -> dict | None:
        url = (f"{self.org_url}/api/data/v9.2/{self.table}"
               f"(sd_idempotencykey='{idempotency_key}')")
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()