"""Plain data types shared between the clients and the rules engine."""

from dataclasses import dataclass, field


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
