"""Read-only GitLab API client: fetches the merge request under validation."""

import logging
import time
from urllib.parse import quote

import requests

from .models import ApiError, MergeRequest

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0


class GitLabClient:
    """Fetches merge requests (and their commits) from the GitLab REST API."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        session: requests.Session | None = None,
    ):
        self._base = base_url.rstrip("/")
        self._session = session or requests.Session()
        if token:
            self._session.headers["PRIVATE-TOKEN"] = token

    def fetch_merge_request(self, project: str, iid: int) -> MergeRequest:
        """Fetch an MR and its commits; raise ApiError if it can't be read."""
        # Project paths like "sztomi/mr-validator-homework" must be
        # URL-encoded into a single path segment ("sztomi%2Fmr-...").
        encoded = quote(project, safe="")
        mr_url = f"{self._base}/api/v4/projects/{encoded}/merge_requests/{iid}"
        data = self._request(mr_url).json()
        commits = self._fetch_all_commits(mr_url)
        return MergeRequest(
            project=project,
            iid=iid,
            title=data["title"],
            source_branch=data["source_branch"],
            description=data.get("description") or "",
            commit_messages=[commit["message"] for commit in commits],
            is_draft=data.get("draft", False),
            web_url=data.get("web_url", ""),
        )

    def _fetch_all_commits(self, mr_url: str) -> list[dict]:
        """Collect every commit of the MR, following GitLab's pagination."""
        commits: list[dict] = []
        page: int | None = 1
        while page is not None:
            response = self._request(
                f"{mr_url}/commits", params={"per_page": 100, "page": page}
            )
            commits.extend(response.json())
            next_page = response.headers.get("X-Next-Page") or ""
            page = int(next_page) if next_page else None
        return commits

    def _request(self, url: str, params: dict | None = None) -> requests.Response:
        """GET a GitLab URL, mapping any failure to ApiError."""
        started = time.monotonic()
        try:
            response = self._session.get(url, params=params, timeout=_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            raise ApiError(f"GitLab request failed: {error}") from error
        log.debug(
            "GET %s params=%s -> HTTP %s (%.0f ms)",
            url, params, response.status_code,
            (time.monotonic() - started) * 1000,
        )
        if response.status_code == 404:
            # Unlike a missing Jira ticket (which is rule 3 data), a missing
            # MR means there is nothing to validate: the gate is misconfigured.
            raise ApiError(
                f"GitLab returned 404 for {url} — check the project path, "
                "the MR number, and (for private projects) the token"
            )
        if not response.ok:
            raise ApiError(f"GitLab returned HTTP {response.status_code} for {url}")
        return response
