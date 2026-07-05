"""The pre-merge rules.

Every rule is evaluated (no short-circuiting) so the CI log shows the
developer every problem at once. Each rule returns a RuleResult whose
detail says what is wrong and what to do next.
"""

from dataclasses import dataclass

from .models import MergeRequest, Ticket

# The workflow states a referenced ticket must be in for the MR to merge.
# Per the team convention, "Won't Do" does NOT count: an MR for cancelled
# work should not be merged without a human taking another look.
ACCEPTED_STATES = frozenset({"In Review", "Done"})


@dataclass(frozen=True)
class RuleResult:
    """The outcome of one rule: its name, pass/fail, and a developer-facing detail."""

    name: str
    passed: bool
    detail: str


def _check_not_draft(merge_request: MergeRequest) -> RuleResult:
    """Rule 1: the MR must not be marked as Draft."""
    if merge_request.is_draft:
        return RuleResult(
            "MR is not a draft",
            passed=False,
            detail="the MR is marked as Draft; mark it ready before merging",
        )
    return RuleResult("MR is not a draft", passed=True, detail="")


def _check_has_refs(refs: dict[str, list[str]]) -> RuleResult:
    """Rule 2: the MR must reference at least one Jira ticket."""
    name = "MR references at least one Jira ticket"
    if not refs:
        return RuleResult(
            name,
            passed=False,
            detail=(
                "no WMS-* ticket found in the title, branch name, description "
                "or commit messages; add the ticket key to the MR title, "
                "e.g. 'WMS-1234: Add foo'"
            ),
        )
    found = ", ".join(
        f"{key} (found in: {', '.join(places)})" for key, places in refs.items()
    )
    return RuleResult(name, passed=True, detail=found)


def _check_tickets_exist(tickets: dict[str, Ticket | None]) -> RuleResult:
    """Rule 3: every referenced ticket must exist in Jira (no 404s)."""
    name = "All referenced tickets exist in Jira"
    if not tickets:
        return RuleResult(name, passed=True, detail="no tickets to check")
    missing = sorted(key for key, ticket in tickets.items() if ticket is None)
    if missing:
        return RuleResult(
            name,
            passed=False,
            detail=(
                f"not found in Jira: {', '.join(missing)}; "
                "fix the ticket key or create the ticket"
            ),
        )
    return RuleResult(name, passed=True, detail="")


def _check_ticket_states(tickets: dict[str, Ticket | None]) -> RuleResult:
    """Rule 4: every existing referenced ticket must be In Review or Done."""

    name = "All referenced tickets are in an accepted state"
    existing = [ticket for ticket in tickets.values() if ticket is not None]
    if not existing:
        return RuleResult(name, passed=True, detail="no tickets to check")
    wrong = [ticket for ticket in existing if ticket.status not in ACCEPTED_STATES]
    if wrong:
        listing = ", ".join(f"{ticket.key} is '{ticket.status}'" for ticket in wrong)
        accepted = " or ".join(sorted(ACCEPTED_STATES))
        return RuleResult(
            name,
            passed=False,
            detail=f"{listing}; tickets must be {accepted} before merging",
        )
    listing = ", ".join(f"{ticket.key} is '{ticket.status}'" for ticket in existing)
    return RuleResult(name, passed=True, detail=listing)


def evaluate(
    merge_request: MergeRequest,
    refs: dict[str, list[str]],
    tickets: dict[str, Ticket | None],
) -> list[RuleResult]:
    """Run every rule and return all results, in reporting order."""
    return [
        _check_not_draft(merge_request),
        _check_has_refs(refs),
        _check_tickets_exist(tickets),
        _check_ticket_states(tickets),
    ]
