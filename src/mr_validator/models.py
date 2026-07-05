"""The shared vocabulary of the package: plain data types and the one
exception that crosses module boundaries."""

from dataclasses import dataclass, field


class ApiError(Exception):
    """A GitLab or Jira call failed for a reason unrelated to the MR itself.

    Network trouble, timeouts, unexpected HTTP statuses, bad configuration.
    The CLI maps this to exit code 2 so CI can tell "the MR is invalid"
    (exit 1) apart from "the validator could not do its job" (exit 2).
    """


@dataclass(frozen=True)
class MergeRequest:
    """The parts of a GitLab merge request the validator cares about."""

    project: str
    iid: int
    title: str
    source_branch: str
    description: str
    commit_messages: list[str] = field(default_factory=list)
    is_draft: bool = False
    web_url: str = ""


@dataclass(frozen=True)
class Ticket:
    """A Jira issue, reduced to what the rules need."""

    key: str
    status: str
    summary: str = ""
