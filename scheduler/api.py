"""Read-only adapter for the documented Triweb planning endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import AVAILABILITY_API_URL, PROJECTS_API_URL, verify_tls


class TriwebApiError(RuntimeError):
    """A useful, display-safe exception for a failed API refresh."""


@dataclass(frozen=True)
class TriwebApiClient:
    timeout_seconds: int = 30
    tls_verified: bool = verify_tls()

    def _get_list(self, url: str, label: str) -> list[dict[str, Any]]:
        try:
            response = requests.get(url, timeout=self.timeout_seconds, verify=self.tls_verified)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TriwebApiError(f"Could not refresh {label}: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise TriwebApiError(f"{label} returned invalid JSON.") from exc
        if not isinstance(payload, list):
            raise TriwebApiError(f"{label} returned {type(payload).__name__}; expected a JSON list.")
        if not all(isinstance(item, dict) for item in payload):
            raise TriwebApiError(f"{label} contains a non-object record.")
        return payload

    def fetch_availability(self) -> list[dict[str, Any]]:
        return self._get_list(AVAILABILITY_API_URL, "availability API")

    def fetch_projects(self) -> list[dict[str, Any]]:
        return self._get_list(PROJECTS_API_URL, "projects API")


class AssignmentRegistrationUnavailable(RuntimeError):
    """Raised instead of inventing an unsafe Triweb write call."""


class AssignmentRegistrar:
    """Deliberately isolated future write adapter.

    The supplied endpoints expose data via GET. Their OPTIONS response is
    authenticated and does not disclose a public assignment contract. Supply
    an official endpoint and payload mapping before enabling registration.
    """

    is_configured = False

    def register(self, assignment: dict[str, Any]) -> None:
        raise AssignmentRegistrationUnavailable(
            "Assignment registration is disabled: no official Triweb write endpoint "
            "or payload contract has been supplied. The assignment remains pending."
        )
