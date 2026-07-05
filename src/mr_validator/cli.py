"""Command-line entry point.

Usage examples:

    mr-validator https://gitlab.com/sztomi/mr-validator-homework/-/merge_requests/1
    mr-validator 1 --project sztomi/mr-validator-homework

Exit codes:
    0  the MR passes all rules and may be merged
    1  the MR fails at least one rule
    2  the validator could not do its job (bad arguments, network trouble,
       MR not found, unexpected API responses)
"""

import argparse
import os
import re
import sys

from . import rules_engine
from .errors import ApiError
from .extractor import extract_ticket_refs
from .gitlab_client import GitLabClient
from .jira_client import JiraClient
from .logger import Logger

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2

#Regex to parse MR URLs like https://gitlab.com/<project>/-/merge_requests/<iid>
_MR_URL_RE = re.compile(r"^(?P<base>https?://[^/]+)/(?P<project>.+?)/-/merge_requests/(?P<iid>\d+)/?$")


def parse_mr_url(url: str) -> tuple[str, str, int]:
    """Split an MR web URL into (gitlab base URL, project path, MR IID)."""
    match = _MR_URL_RE.match(url)
    if not match:
        raise ValueError(f"not a merge request URL: {url!r} ""(expected .../<project>/-/merge_requests/<iid>)")
    return match["base"], match["project"], int(match["iid"])


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser: MR target, endpoints/tokens, output options."""
    parser = argparse.ArgumentParser(
        prog="mr-validator",
        description="Pre-merge gate: checks that a GitLab MR references "
        "Jira tickets in a mergeable state.",
    )
    parser.add_argument(
        "mr",
        help="MR URL (https://gitlab.com/<project>/-/merge_requests/<iid>), "
        "or a bare IID when --project is given",
    )
    parser.add_argument(
        "--project",
        help="GitLab project path, e.g. sztomi/mr-validator-homework "
        "(only needed when MR is given as a bare IID)",
    )
    parser.add_argument(
        "--gitlab-url",
        default=os.environ.get("MR_VALIDATOR_GITLAB_URL", "https://gitlab.com"),
        help="GitLab base URL [env: MR_VALIDATOR_GITLAB_URL] (default: %(default)s)",
    )
    parser.add_argument(
        "--gitlab-token",
        default=os.environ.get("MR_VALIDATOR_GITLAB_TOKEN"),
        help="GitLab token, only needed for private projects "
        "[env: MR_VALIDATOR_GITLAB_TOKEN]",
    )
    parser.add_argument(
        "--jira-url",
        default=os.environ.get("MR_VALIDATOR_JIRA_URL", "http://localhost:8080"),
        help="Jira base URL [env: MR_VALIDATOR_JIRA_URL] (default: %(default)s)",
    )
    parser.add_argument(
        "--jira-token",
        default=os.environ.get("MR_VALIDATOR_JIRA_TOKEN"),
        help="Jira bearer token [env: MR_VALIDATOR_JIRA_TOKEN]",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="show diagnostic output"
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colorize the summary (default: %(default)s — only when stdout "
        "is a terminal; NO_COLOR is respected)",
    )
    return parser


def resolve_target(args: argparse.Namespace) -> tuple[str, str, int]:
    """Work out (gitlab base URL, project, iid) from the CLI arguments."""
    if args.mr.startswith(("http://", "https://")):
        return parse_mr_url(args.mr)
    if args.project and args.mr.isdigit():
        return args.gitlab_url, args.project, int(args.mr)
    raise ValueError("pass either a full MR URL, or a numeric IID together with --project")


def run(args: argparse.Namespace, logger: Logger) -> int:
    """Fetch the MR, extract refs, look up tickets, evaluate rules, report."""
    gitlab_url, project, iid = resolve_target(args)
    gitlab = GitLabClient(gitlab_url, token=args.gitlab_token)
    jira = JiraClient(args.jira_url, token=args.jira_token)

    logger.info("fetching %s!%s from %s", project, iid, gitlab_url)
    mr = gitlab.fetch_merge_request(project, iid)

    refs = extract_ticket_refs(mr.title, mr.source_branch, mr.description, mr.commit_messages)

    logger.info("referenced tickets: %s", ", ".join(refs) or "none")
    tickets = {}
    for key in refs:
        ticket = jira.fetch_ticket(key)
        logger.info(
            "%s: %s", key, f"'{ticket.status}'" if ticket else "not found in Jira"
        )
        tickets[key] = ticket

    results = rules_engine.evaluate(mr, refs, tickets)

    logger.mr_header(mr)
    for result in results:
        logger.rule_result(result)
    logger.verdict(results)

    passed = all(r.passed for r in results)
    return EXIT_PASS if passed else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse arguments, run the validation, map errors to exit codes."""
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        # Friendlier than argparse's terse "arguments are required" error,
        # but still a non-zero exit: a gate invoked wrong must not pass.
        parser.print_help()
        return EXIT_ERROR
    args = parser.parse_args(argv)
    logger = Logger(verbose=args.verbose, color=args.color)
    try:
        return run(args, logger)
    except ValueError as exc:
        logger.error(str(exc))
        return EXIT_ERROR
    except ApiError as exc:
        logger.error(str(exc))
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
