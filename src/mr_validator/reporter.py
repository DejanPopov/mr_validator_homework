"""The CI summary — the product of the tool.

The generic output machinery (color handling, the diagnostics channel)
lives in the shared utils package and is usable by any script; this module
adds the mr-validator-specific rendering on top: which MR is being
validated, each rule's PASS/FAIL line, and the final verdict.
"""

from utils.logger import Logger

from .models import MergeRequest
from .rules_engine import RuleResult


class Reporter(Logger):
    """Renders the mr-validator CI summary on top of the generic Logger."""

    def __init__(self, verbose: bool = False, stream=None, color: str = "auto"):
        super().__init__("mr_validator", verbose=verbose, stream=stream, color=color)

    def mr_header(self, merge_request: MergeRequest) -> None:
        """Print which MR is being validated, with its title and URL."""
        name = self.paint(f"{merge_request.project}!{merge_request.iid}", "bold")
        title = self.paint(f'"{merge_request.title}"', "bold")
        self.write(f"Validating {name} — {title}")
        if merge_request.web_url:
            self.write(self.paint(merge_request.web_url, "dim"))
        self.write("")

    def rule_result(self, result: RuleResult) -> None:
        """Print one rule's PASS/FAIL line plus its detail, if any."""
        if result.passed:
            status = self.paint("PASS", "green", "bold")
        else:
            status = self.paint("FAIL", "red", "bold")
        self.write(f"{status}  {result.name}")
        if result.detail:
            style = "yellow" if not result.passed else "dim"
            self.write(f"      {self.paint(result.detail, style)}")

    def verdict(self, results: list[RuleResult]) -> None:
        """Print the final PASS/FAIL verdict line summarizing all rules."""
        failed = sum(1 for result in results if not result.passed)
        self.write("")
        if failed:
            text = (
                f"RESULT: FAIL — {failed} of {len(results)} rules failed; "
                "this MR must not be merged yet"
            )
            self.write(self.paint(text, "red", "bold"))
        else:
            text = f"RESULT: PASS — all {len(results)} rules passed"
            self.write(self.paint(text, "green", "bold"))
