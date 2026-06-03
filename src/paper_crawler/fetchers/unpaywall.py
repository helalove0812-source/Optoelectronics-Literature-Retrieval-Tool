from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests

UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"


class SupportsGet(Protocol):
    def get(self, url: str, params: dict[str, object], timeout: int): ...


@dataclass(slots=True)
class UnpaywallClient:
    contact_email: str
    session: SupportsGet | requests.Session | None = None
    request_timeout: int = 30

    def lookup(self, doi: str) -> dict[str, object]:
        session = self.session or requests.Session()
        response = session.get(
            f"{UNPAYWALL_API_BASE}/{doi}",
            params={"email": self.contact_email},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        best_oa_location = payload.get("best_oa_location") or {}

        return {
            "is_oa": bool(payload.get("is_oa")),
            "pdf_url": best_oa_location.get("url_for_pdf"),
            "landing_url": best_oa_location.get("url"),
        }
