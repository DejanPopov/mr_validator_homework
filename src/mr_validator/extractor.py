"""Extract Jira ticket references from the parts of a merge request.

References are searched in the MR title, source branch name, description,
and commit messages. Markdown code blocks in the description are ignored:
a ticket key inside a code example is not a reference to work being merged.
"""

import re

# A ticket key must not be glued to surrounding letters/digits ("XWMS-1234")
# and the number must be complete ("WMS-1234" never matches as "WMS-123").
# A trailing hyphen is allowed so branch names like
# "feature/WMS-1234-add-foo" still match.
_TICKET_RE = re.compile(r"(?<![A-Za-z0-9])WMS-(\d+)(?!\d)")

# Fenced code blocks (```...``` or ~~~...~~~) and inline code spans (`...`).
_FENCED_BLOCK_RE = re.compile(r"^(```|~~~).*?^\1[^\S\n]*$", re.DOTALL | re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_code(markdown: str) -> str:
    """Remove fenced code blocks and inline code spans from markdown text."""
    without_blocks = _FENCED_BLOCK_RE.sub("", markdown)
    return _INLINE_CODE_RE.sub("", without_blocks)


def _find_keys(text: str) -> list[str]:
    """Return every WMS-* ticket key in the text, in order of appearance."""
    return [f"WMS-{number}" for number in _TICKET_RE.findall(text)]


def extract_ticket_refs(
    title: str,
    branch: str,
    description: str,
    commit_messages: list[str],
) -> dict[str, list[str]]:
    """Return every referenced ticket key mapped to the places it was found.

    Example: {"WMS-1001": ["title", "branch"], "WMS-1010": ["commits"]}
    Keys are ordered by first appearance (title, branch, description, commits).
    """
    sources = [
        ("title", title),
        ("branch", branch),
        ("description", _strip_code(description)),
        ("commits", "\n".join(commit_messages)),
    ]
    refs: dict[str, list[str]] = {}
    for source_name, text in sources:
        for key in _find_keys(text):
            locations = refs.setdefault(key, [])
            if source_name not in locations:
                locations.append(source_name)
    return refs
