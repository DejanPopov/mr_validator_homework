"""Read-only Jira API client: looks up referenced tickets.

Works against the provided mock server and, unchanged, against real Jira
(the mock mirrors the REST API v3 response shape).
"""

import logging
import time
from http import HTTPStatus

import requests

from .models import ApiError, Ticket

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
_MS_PER_SECOND = 1000


class JiraClient:
    """Looks up issues on the Jira REST API v3 (mock or real)."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        session: requests.Session | None = None,
    ):
        self._base = base_url.rstrip("/")
        self._session = session or requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def fetch_ticket(self, key: str) -> Ticket | None:
        """Return the ticket, or None if it does not exist in Jira.

        A 404 is expected data (it is exactly what rule 3 checks for),
        so it is returned as None rather than raised.
        """
        url = f"{self._base}/rest/api/3/issue/{key}"
        started = time.monotonic()
        try:
            response = self._session.get(url, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            raise ApiError(f"Jira request failed: {error}") from error
        log.debug(
            "GET %s -> HTTP %s (%.0f ms)",
            url, response.status_code, (time.monotonic() - started) * _MS_PER_SECOND,
        )
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        if not response.ok:
            raise ApiError(f"Jira returned HTTP {response.status_code} for {url}")
        data = response.json()
        fields = data["fields"]
        return Ticket(
            key=data["key"],
            status=fields["status"]["name"],
            summary=fields.get("summary", ""),
        )
