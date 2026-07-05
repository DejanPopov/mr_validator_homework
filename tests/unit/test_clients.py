import pytest
import requests

from mr_validator.errors import ApiError
from mr_validator.gitlab_client import GitLabClient
from mr_validator.jira_client import JiraClient
from mr_validator.models import Ticket


class FakeResponse:
    """A minimal stand-in for requests.Response: status, JSON payload, headers."""

    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    @property
    def ok(self):
        """Mirror requests.Response.ok: True below 400."""
        return self.status_code < 400

    def json(self):
        """Return the canned payload."""
        return self._payload


class FakeSession:
    """Stands in for requests.Session; serves queued responses per URL and records calls."""

    def __init__(self):
        self.headers = {}
        self.calls = []
        self._routes = {}

    def route(self, url, *responses):
        """Register the responses this URL returns, in order."""
        self._routes.setdefault(url, []).extend(responses)

    def get(self, url, params=None, timeout=None):
        """Record the call and pop the next queued response for the URL."""
        self.calls.append((url, params, timeout))
        queue = self._routes[url]
        return queue.pop(0) if len(queue) > 1 else queue[0]


GITLAB = "https://gitlab.example.com"
MR_URL = f"{GITLAB}/api/v4/projects/group%2Frepo/merge_requests/7"

MR_PAYLOAD = {
    "title": "WMS-1001: Add auth",
    "source_branch": "feature/WMS-1001-auth",
    "description": None,  # GitLab sends null for an empty description
    "draft": True,
    "web_url": "https://gitlab.example.com/group/repo/-/merge_requests/7",
}


def make_gitlab(session):
    """Build a GitLabClient wired to the given fake session."""
    return GitLabClient(GITLAB, session=session)


class TestGitLabClient:
    """GitLabClient maps API payloads to MergeRequest and API trouble to ApiError."""

    def test_builds_merge_request_from_api_payload(self):
        """The JSON payload becomes a MergeRequest, with null description normalized."""
        session = FakeSession()
        session.route(MR_URL, FakeResponse(payload=MR_PAYLOAD))
        session.route(
            f"{MR_URL}/commits",
            FakeResponse(payload=[{"message": "WMS-1001: add auth\n"}]),
        )

        mr = make_gitlab(session).fetch_merge_request("group/repo", 7)

        assert mr.title == "WMS-1001: Add auth"
        assert mr.source_branch == "feature/WMS-1001-auth"
        assert mr.description == ""  # null normalized to empty string
        assert mr.is_draft is True
        assert mr.commit_messages == ["WMS-1001: add auth\n"]

    def test_project_path_is_url_encoded(self):
        """'group/repo' must be sent as one path segment: 'group%2Frepo'."""
        session = FakeSession()
        session.route(MR_URL, FakeResponse(payload=MR_PAYLOAD))
        session.route(f"{MR_URL}/commits", FakeResponse(payload=[]))

        make_gitlab(session).fetch_merge_request("group/repo", 7)

        assert session.calls[0][0] == MR_URL  # contains group%2Frepo

    def test_commit_pagination_follows_next_page_header(self):
        """All commit pages are fetched, so a 300-commit MR is fully scanned."""
        session = FakeSession()
        session.route(MR_URL, FakeResponse(payload=MR_PAYLOAD))
        session.route(
            f"{MR_URL}/commits",
            FakeResponse(payload=[{"message": "one"}], headers={"X-Next-Page": "2"}),
            FakeResponse(payload=[{"message": "two"}], headers={"X-Next-Page": ""}),
        )

        mr = make_gitlab(session).fetch_merge_request("group/repo", 7)

        assert mr.commit_messages == ["one", "two"]
        pages = [params["page"] for url, params, _ in session.calls if params]
        assert pages == [1, 2]

    def test_missing_mr_raises_api_error(self):
        """A 404 for the MR itself is a config problem, not a rule verdict."""
        session = FakeSession()
        session.route(MR_URL, FakeResponse(status_code=404))

        with pytest.raises(ApiError, match="404"):
            make_gitlab(session).fetch_merge_request("group/repo", 7)

    def test_token_is_sent_as_private_token_header(self):
        """The GitLab token travels in the PRIVATE-TOKEN header."""
        session = FakeSession()
        GitLabClient(GITLAB, token="secret", session=session)
        assert session.headers["PRIVATE-TOKEN"] == "secret"

    def test_server_error_raises_api_error(self):
        """A GitLab 5xx is infrastructure trouble and must surface as ApiError."""
        session = FakeSession()
        session.route(MR_URL, FakeResponse(status_code=503))

        with pytest.raises(ApiError, match="503"):
            make_gitlab(session).fetch_merge_request("group/repo", 7)

    def test_connection_failure_raises_api_error(self):
        """A network-level failure must surface as ApiError, not a raw exception."""

        class BrokenSession(FakeSession):
            """A session whose every request fails at the network level."""

            def get(self, url, params=None, timeout=None):
                """Simulate a refused connection."""
                raise requests.ConnectionError("connection refused")

        with pytest.raises(ApiError, match="GitLab request failed"):
            make_gitlab(BrokenSession()).fetch_merge_request("group/repo", 7)


JIRA = "http://localhost:8080"
ISSUE_URL = f"{JIRA}/rest/api/3/issue/WMS-1001"

ISSUE_PAYLOAD = {
    "key": "WMS-1001",
    "fields": {
        "summary": "Add bearer-token auth",
        "status": {"name": "In Review"},
    },
}


class TestJiraClient:
    """JiraClient maps issues to Ticket, 404 to None, and API trouble to ApiError."""

    def test_existing_ticket_is_returned(self):
        """A 200 response becomes a Ticket with key, status, and summary."""
        session = FakeSession()
        session.route(ISSUE_URL, FakeResponse(payload=ISSUE_PAYLOAD))

        ticket = JiraClient(JIRA, session=session).fetch_ticket("WMS-1001")

        assert ticket == Ticket("WMS-1001", "In Review", "Add bearer-token auth")

    def test_missing_ticket_returns_none_not_error(self):
        """A 404 is rule-3 data — it must come back as None, never raise."""
        session = FakeSession()
        session.route(f"{JIRA}/rest/api/3/issue/WMS-9999", FakeResponse(404))

        assert JiraClient(JIRA, session=session).fetch_ticket("WMS-9999") is None

    def test_server_error_raises_api_error(self):
        """A Jira 5xx is infrastructure trouble and must surface as ApiError."""
        session = FakeSession()
        session.route(ISSUE_URL, FakeResponse(500))

        with pytest.raises(ApiError, match="500"):
            JiraClient(JIRA, session=session).fetch_ticket("WMS-1001")

    def test_connection_failure_raises_api_error(self):
        """A network-level failure must surface as ApiError, not a raw exception."""

        class BrokenSession(FakeSession):
            """A session whose every request fails at the network level."""

            def get(self, url, params=None, timeout=None):
                """Simulate a refused connection."""
                raise requests.ConnectionError("connection refused")

        with pytest.raises(ApiError, match="Jira request failed"):
            JiraClient(JIRA, session=BrokenSession()).fetch_ticket("WMS-1001")

    def test_token_is_sent_as_bearer_header(self):
        """The Jira token travels as a Bearer Authorization header."""
        session = FakeSession()
        JiraClient(JIRA, token="secret", session=session)
        assert session.headers["Authorization"] == "Bearer secret"
