from mr_validator.models import MergeRequest, Ticket
from mr_validator.rules_engine import evaluate


def make_mr(**overrides):
    """Build a valid MergeRequest, letting each test override only what it cares about."""
    defaults = dict(
        project="group/repo",
        iid=1,
        title="WMS-1001: Add auth",
        source_branch="feature/WMS-1001-auth",
        description="",
        is_draft=False,
    )
    defaults.update(overrides)
    return MergeRequest(**defaults)


def by_name(results):
    """Index a list of RuleResults by rule name for direct assertions."""
    return {result.name: result for result in results}


REFS = {"WMS-1001": ["title", "branch"]}
TICKETS_OK = {"WMS-1001": Ticket("WMS-1001", "In Review")}


class TestDraftRule:
    """Rule 1: a Draft MR must not be merged."""

    def test_draft_mr_fails(self):
        """An MR marked Draft fails the gate."""
        results = by_name(evaluate(make_mr(is_draft=True), REFS, TICKETS_OK))
        assert not results["MR is not a draft"].passed

    def test_ready_mr_passes(self):
        """A ready (non-draft) MR passes rule 1."""
        results = by_name(evaluate(make_mr(), REFS, TICKETS_OK))
        assert results["MR is not a draft"].passed

    def test_other_rules_still_evaluated_for_draft(self):
        """Draft must not short-circuit: the developer sees all problems in one run."""
        results = evaluate(make_mr(is_draft=True), REFS, TICKETS_OK)
        assert len(results) == 4


class TestRefsRule:
    """Rule 2: the MR must reference at least one Jira ticket."""

    RULE = "MR references at least one Jira ticket"

    def test_zero_refs_fails(self):
        """No reference anywhere means the gate fails."""
        results = by_name(evaluate(make_mr(), {}, {}))
        assert not results[self.RULE].passed

    def test_refs_pass_and_detail_shows_provenance(self):
        """The passing detail names each ticket and where it was found."""
        results = by_name(evaluate(make_mr(), REFS, TICKETS_OK))
        assert results[self.RULE].passed
        assert "WMS-1001 (found in: title, branch)" in results[self.RULE].detail


class TestExistenceRule:
    """Rule 3: every referenced ticket must exist in Jira."""

    RULE = "All referenced tickets exist in Jira"

    def test_missing_ticket_fails_and_is_named(self):
        """A 404'd ticket fails the rule and is named in the detail."""
        tickets = {"WMS-9999": None}
        results = by_name(evaluate(make_mr(), {"WMS-9999": ["title"]}, tickets))
        assert not results[self.RULE].passed
        assert "WMS-9999" in results[self.RULE].detail

    def test_all_existing_passes(self):
        """When every referenced ticket exists, rule 3 passes."""
        results = by_name(evaluate(make_mr(), REFS, TICKETS_OK))
        assert results[self.RULE].passed

    def test_no_refs_passes_vacuously(self):
        """With zero refs there is nothing to check; rule 2 carries the failure."""
        results = by_name(evaluate(make_mr(), {}, {}))
        assert results[self.RULE].passed
        assert "no tickets" in results[self.RULE].detail


class TestStateRule:
    """Rule 4: every existing referenced ticket must be In Review or Done."""

    RULE = "All referenced tickets are in an accepted state"

    def test_in_review_and_done_pass(self):
        """In Review and Done are the two mergeable states."""
        tickets = {
            "WMS-1001": Ticket("WMS-1001", "In Review"),
            "WMS-1003": Ticket("WMS-1003", "Done"),
        }
        results = by_name(evaluate(make_mr(), REFS, tickets))
        assert results[self.RULE].passed

    def test_open_ticket_fails_with_status_in_detail(self):
        """An Open ticket blocks the merge and its state is shown to the developer."""
        tickets = {"WMS-1011": Ticket("WMS-1011", "Open")}
        results = by_name(evaluate(make_mr(), {"WMS-1011": ["title"]}, tickets))
        assert not results[self.RULE].passed
        assert "WMS-1011 is 'Open'" in results[self.RULE].detail

    def test_in_progress_ticket_fails(self):
        """An In Progress ticket blocks the merge."""
        tickets = {"WMS-1010": Ticket("WMS-1010", "In Progress")}
        results = by_name(evaluate(make_mr(), {"WMS-1010": ["title"]}, tickets))
        assert not results[self.RULE].passed

    def test_wont_do_ticket_fails(self):
        """Won't Do is deliberately not mergeable: cancelled work needs human eyes."""
        tickets = {"WMS-1020": Ticket("WMS-1020", "Won't Do")}
        results = by_name(evaluate(make_mr(), {"WMS-1020": ["title"]}, tickets))
        assert not results[self.RULE].passed

    def test_one_bad_ticket_among_good_ones_fails(self):
        """A single non-mergeable ticket blocks the MR regardless of the others."""
        tickets = {
            "WMS-1001": Ticket("WMS-1001", "In Review"),
            "WMS-1010": Ticket("WMS-1010", "In Progress"),
        }
        results = by_name(evaluate(make_mr(), REFS, tickets))
        assert not results[self.RULE].passed

    def test_missing_tickets_are_not_double_reported(self):
        """A 404 ticket already fails rule 3; rule 4 must not report it again."""
        tickets = {"WMS-9999": None}
        results = by_name(evaluate(make_mr(), {"WMS-9999": ["title"]}, tickets))
        assert results[self.RULE].passed
