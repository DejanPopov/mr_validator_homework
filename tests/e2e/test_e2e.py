"""End-to-end tests: the real CLI, the real GitLab API, the real mock Jira.

Each test runs the installed CLI as a subprocess (python -m mr_validator.cli)
against the public fixture project on gitlab.com, with the provided
mock_jira.py spawned as a child process on a free port. Nothing is faked
beyond what the homework itself provides.

Requires network access to gitlab.com. Deselect with:  pytest -m "not e2e"
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT = "sztomi/mr-validator-homework"
MR_URL = f"https://gitlab.com/{PROJECT}/-/merge_requests"


def _free_port() -> int:
    """Ask the OS for a currently free TCP port."""
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


def _wait_until_serving(port: int, timeout: float = 5.0) -> None:
    """Block until something accepts connections on the port, or fail loudly."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"mock Jira did not start on port {port} within {timeout}s")


@pytest.fixture(scope="session")
def mock_jira_url():
    """Spawn the provided mock_jira.py on a free port for the whole session.

    The port is overridden by importing the module and patching its PORT
    constant before main() runs — mock_jira.py itself stays unmodified.
    """
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import mock_jira; mock_jira.PORT = {port}; mock_jira.main()",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_serving(port)
        yield f"http://localhost:{port}"
    finally:
        process.terminate()
        process.wait(timeout=5)


def run_validator(*args: str, jira_url: str) -> subprocess.CompletedProcess:
    """Run the CLI exactly as CI would: a subprocess, configured via env."""
    return subprocess.run(
        [sys.executable, "-m", "mr_validator.cli", *args],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "MR_VALIDATOR_JIRA_URL": jira_url},
    )


# The complete fixture inventory: every open MR in the project, the exit code
# it must produce, and the evidence that must appear in the summary. This
# table IS the acceptance spec of the tool.
FIXTURE_VERDICTS = [
    # iid, exit, expected stdout snippets, scenario
    (1, 0, ["RESULT: PASS"], "ref everywhere, ticket In Review"),
    (2, 0, ["RESULT: PASS"], "ticket Done"),
    (3, 0, ["RESULT: PASS"], "two tickets, both mergeable"),
    (4, 0, ["WMS-1004 (found in: branch)", "RESULT: PASS"], "branch-name fallback"),
    (5, 0, ["WMS-1101 (found in: description)", "RESULT: PASS"], "description only"),
    (6, 1, ["WMS-1020 (found in: commits)", "WMS-1020 is 'Won't Do'"], "commits only + Won't Do"),
    (7, 1, ["FAIL  MR is not a draft"], "draft MR"),
    (8, 1, ["FAIL  MR references at least one Jira ticket"], "zero refs"),
    (9, 1, ["not found in Jira: WMS-9999"], "nonexistent ticket"),
    (10, 1, ["WMS-1011 is 'Open'"], "ticket Open"),
    (11, 1, ["WMS-1010 is 'In Progress'"], "ticket In Progress"),
    (12, 1, ["WMS-1010 is 'In Progress'", "RESULT: FAIL"], "one bad ticket among good"),
    (13, 1, ["FAIL  MR references at least one Jira ticket"], "ref only inside code block"),
]


@pytest.mark.parametrize(
    "iid,expected_exit,snippets",
    [(iid, code, snippets) for iid, code, snippets, _ in FIXTURE_VERDICTS],
    ids=[f"mr{iid}-{scenario.replace(' ', '-')}" for iid, _, _, scenario in FIXTURE_VERDICTS],
)
def test_every_fixture_mr_gets_the_right_verdict(mock_jira_url, iid, expected_exit, snippets):
    """Each fixture MR must produce its expected exit code and name its reason."""
    result = run_validator(f"{MR_URL}/{iid}", jira_url=mock_jira_url)

    assert result.returncode == expected_exit, (
        f"MR !{iid}: expected exit {expected_exit}, got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    for snippet in snippets:
        assert snippet in result.stdout, (
            f"MR !{iid}: expected {snippet!r} in summary\nstdout:\n{result.stdout}"
        )


class TestCliContracts:
    """The promises CI relies on, beyond per-MR verdicts."""

    def test_iid_plus_project_form_matches_url_form(self, mock_jira_url):
        """Both ways of naming an MR must produce identical results."""
        by_url = run_validator(f"{MR_URL}/1", jira_url=mock_jira_url)
        by_iid = run_validator("1", "--project", PROJECT, jira_url=mock_jira_url)
        assert by_iid.returncode == by_url.returncode == 0
        assert by_iid.stdout == by_url.stdout

    def test_nonexistent_mr_exits_2_not_1(self, mock_jira_url):
        """A missing MR is a config problem (exit 2), never a rule verdict (exit 1)."""
        result = run_validator(f"{MR_URL}/99999", jira_url=mock_jira_url)
        assert result.returncode == 2
        assert "404" in result.stderr

    def test_unreachable_jira_exits_2_with_diagnostic(self):
        """Jira being down is infrastructure trouble: exit 2 and say so on stderr."""
        dead_port = _free_port()  # allocated then released: nothing listens
        result = run_validator(
            f"{MR_URL}/1", jira_url=f"http://localhost:{dead_port}"
        )
        assert result.returncode == 2
        assert "Jira request failed" in result.stderr

    def test_summary_on_stdout_diagnostics_on_stderr(self, mock_jira_url):
        """The parseable summary and the -v telemetry must not share a stream."""
        result = run_validator(f"{MR_URL}/9", "-v", jira_url=mock_jira_url)
        # the parseable product on stdout...
        assert "RESULT: FAIL" in result.stdout
        assert "RESULT" not in result.stderr
        # ...telemetry on stderr, never polluting stdout
        assert "GET https://gitlab.com" in result.stderr
        assert "GET http" not in result.stdout

    def test_piped_output_contains_no_ansi_codes(self, mock_jira_url):
        """With both streams piped (as CI does), auto color must switch off."""
        result = run_validator(f"{MR_URL}/1", jira_url=mock_jira_url)
        assert "\033[" not in result.stdout
        assert "\033[" not in result.stderr
