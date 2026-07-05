from mr_validator.extractor import extract_ticket_refs


def extract(title="", branch="", description="", commits=None):
    """Call extract_ticket_refs with defaults so tests only state what they care about."""
    return extract_ticket_refs(title, branch, description, commits or [])


class TestSources:
    """Refs must be found in each of the four places the task names."""

    def test_finds_key_in_title(self):
        """The MR title is the canonical place for a ticket reference."""
        assert extract(title="WMS-1001: Add auth") == {"WMS-1001": ["title"]}

    def test_finds_key_in_branch(self):
        """The source branch name is the documented fallback location."""
        assert extract(branch="feature/WMS-1004-pagination") == {
            "WMS-1004": ["branch"]
        }

    def test_finds_key_in_description(self):
        """References may also appear in the MR description."""
        assert extract(description="Fixes WMS-1101.") == {"WMS-1101": ["description"]}

    def test_finds_key_in_commit_messages(self):
        """References may also appear in any commit message."""
        assert extract(commits=["WMS-1003: bump SDK", "cleanup"]) == {
            "WMS-1003": ["commits"]
        }

    def test_no_references_returns_empty(self):
        """An MR with no ticket anywhere yields an empty dict (rule 2 fails on this)."""
        assert extract(title="Tiny refactor", branch="refactor/tidy-up") == {}

    def test_finds_key_in_any_commit_not_just_the_first(self):
        """The whole commit list is scanned, not only the newest message."""
        commits = ["initial scaffold", "wire up exporter", "WMS-1020: drop legacy path"]
        assert extract(commits=commits) == {"WMS-1020": ["commits"]}

    def test_several_distinct_keys_in_one_source(self):
        """One source can reference multiple tickets; all must be validated."""
        refs = extract(title="WMS-1001, WMS-1002: combined fixes")
        assert refs == {"WMS-1001": ["title"], "WMS-1002": ["title"]}


class TestProvenance:
    """Each key remembers where it was found, for the CI summary."""

    def test_same_key_in_multiple_sources_is_deduplicated(self):
        """A ticket referenced in several places is one ticket with several locations."""
        refs = extract(
            title="WMS-1001: Add auth",
            branch="feature/WMS-1001-auth",
            description="Implements WMS-1001.",
        )
        assert refs == {"WMS-1001": ["title", "branch", "description"]}

    def test_multiple_keys_ordered_by_first_appearance(self):
        """Deterministic ordering keeps the summary (and tests) stable."""
        refs = extract(
            title="WMS-1001, WMS-1002: combined fixes",
            branch="feature/WMS-1001-1002-combined",
        )
        assert list(refs) == ["WMS-1001", "WMS-1002"]


class TestWordBoundaries:
    """The regex must not match keys glued into other words or numbers."""

    def test_key_glued_to_letters_does_not_match(self):
        """'XWMS-1234' is not a WMS ticket reference."""
        assert extract(description="XWMS-1234 is not a ticket") == {}

    def test_partial_number_is_not_extracted(self):
        """The full ticket number is captured, never a truncated prefix of it."""
        refs = extract(description="see WMS-1234")
        assert refs == {"WMS-1234": ["description"]}

    def test_trailing_hyphen_in_branch_still_matches(self):
        """Branch names like feature/WMS-1001-and-1010 must still match WMS-1001."""
        assert extract(branch="feature/WMS-1001-and-1010") == {"WMS-1001": ["branch"]}

    def test_lowercase_is_not_a_ticket_key(self):
        """Jira keys are uppercase; 'wms-1001' in prose is not a reference."""
        assert extract(description="wms-1001 mentioned casually") == {}


class TestMarkdownCodeIsIgnored:
    """A key inside example code is not a reference to work being merged (MR !13)."""

    def test_key_inside_fenced_block_is_ignored(self):
        """A ticket key inside ``` fences is an example, not a reference."""
        description = "Example reference:\n\n```\nWMS-1001\n```"
        assert extract(description=description) == {}

    def test_key_inside_inline_code_is_ignored(self):
        """A ticket key inside `backticks` is an example, not a reference."""
        assert extract(description="run `validate WMS-1001` locally") == {}

    def test_key_outside_code_block_still_counts(self):
        """Stripping a code block must not swallow references around it."""
        description = "Fixes WMS-1002.\n\n```\nWMS-1001\n```"
        assert extract(description=description) == {"WMS-1002": ["description"]}

    def test_code_blocks_only_stripped_from_description(self):
        """Only the description is markdown; backticks elsewhere are literal text."""
        assert extract(title="`WMS-1001` quoted title") == {"WMS-1001": ["title"]}
