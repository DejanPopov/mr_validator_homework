import io

import pytest

from mr_validator.cli import EXIT_ERROR, build_parser, main, parse_mr_url, resolve_target
from mr_validator.logger import Logger
from mr_validator.models import MergeRequest
from mr_validator.rules_engine import RuleResult


class TestParseMrUrl:
    """MR web URLs are split into (base URL, project path, IID)."""

    def test_parses_gitlab_com_url(self):
        """The canonical gitlab.com MR URL parses into its three parts."""
        base, project, iid = parse_mr_url(
            "https://gitlab.com/sztomi/mr-validator-homework/-/merge_requests/13"
        )
        assert base == "https://gitlab.com"
        assert project == "sztomi/mr-validator-homework"
        assert iid == 13

    def test_parses_nested_group_and_self_hosted_instance(self):
        """Nested groups and self-hosted GitLab hosts parse the same way."""
        base, project, iid = parse_mr_url(
            "https://git.corp.example/team/sub/repo/-/merge_requests/7"
        )
        assert base == "https://git.corp.example"
        assert project == "team/sub/repo"
        assert iid == 7

    def test_rejects_non_mr_url(self):
        """A URL that is not an MR URL raises with a hint of the expected shape."""
        with pytest.raises(ValueError, match="not a merge request URL"):
            parse_mr_url("https://gitlab.com/sztomi/mr-validator-homework")


class TestResolveTarget:
    """The CLI accepts a full MR URL or a bare IID plus --project."""

    def parse(self, *argv):
        """Parse argv through the real argument parser."""
        return build_parser().parse_args(argv)

    def test_full_url_wins(self):
        """A full URL carries its own host, project, and IID."""
        args = self.parse("https://gitlab.com/group/repo/-/merge_requests/5")
        assert resolve_target(args) == ("https://gitlab.com", "group/repo", 5)

    def test_bare_iid_with_project(self):
        """A numeric IID combines with --project and the configured GitLab URL."""
        args = self.parse("5", "--project", "group/repo")
        assert resolve_target(args) == ("https://gitlab.com", "group/repo", 5)

    def test_bare_iid_without_project_is_an_error(self):
        """A bare IID without --project cannot identify an MR."""
        with pytest.raises(ValueError, match="--project"):
            resolve_target(self.parse("5"))


class TestNoArguments:
    """Invocation with no arguments must help the user but never look like a pass."""

    def test_no_args_prints_help_and_exits_nonzero(self, capsys):
        """No arguments prints the full help but exits 2 — a gate invoked wrong must not pass."""
        code = main([])
        assert code == EXIT_ERROR
        out = capsys.readouterr().out
        assert "usage: mr-validator" in out
        assert "--project" in out

    def test_dash_h_prints_help_and_exits_zero(self, capsys):
        """-h is an explicit request for help, so it exits 0 (argparse built-in)."""
        with pytest.raises(SystemExit) as excinfo:
            main(["-h"])
        assert excinfo.value.code == 0
        assert "usage: mr-validator" in capsys.readouterr().out


class TestLoggerOutput:
    """The Logger renders the summary a CI log shows to developers."""

    def render(self, results):
        """Render a header, the given rule results, and the verdict to a string."""
        stream = io.StringIO()
        logger = Logger(stream=stream)
        mr = MergeRequest(
            project="group/repo",
            iid=7,
            title="WMS-1001: Add auth",
            source_branch="feature/x",
            description="",
        )
        logger.mr_header(mr)
        for result in results:
            logger.rule_result(result)
        logger.verdict(results)
        return stream.getvalue()

    def test_failing_run_shows_fail_lines_and_verdict(self):
        """Failed rules appear as FAIL with their detail, and the verdict says FAIL."""
        out = self.render(
            [
                RuleResult("MR is not a draft", True, ""),
                RuleResult("MR references at least one Jira ticket", False, "no WMS-* ticket found"),
            ]
        )
        assert "PASS  MR is not a draft" in out
        assert "FAIL  MR references at least one Jira ticket" in out
        assert "no WMS-* ticket found" in out
        assert "RESULT: FAIL — 1 of 2 rules failed" in out

    def test_passing_run_ends_with_pass_verdict(self):
        """When every rule passes, the verdict line says PASS."""
        out = self.render([RuleResult("MR is not a draft", True, "")])
        assert "RESULT: PASS — all 1 rules passed" in out


class TestColors:
    """Color is cosmetic except for one hard promise: clean piped output."""

    def test_non_terminal_output_gets_no_ansi_codes(self):
        """Piped/redirected output (CI logs, files) must never contain escape codes."""
        stream = io.StringIO()
        logger = Logger(stream=stream)  # StringIO.isatty() is False
        logger.rule_result(RuleResult("MR is not a draft", True, ""))
        assert "\033[" not in stream.getvalue()
