"""All output of the tool, in one place.

Two channels, deliberately separate:

- diagnostics (debug/info/error) go through stdlib logging to stderr;
  --verbose turns the chatty levels on. Modules elsewhere in the package
  log via logging.getLogger(__name__), which this class configures.
- the CI summary (mr_header/rule_result/verdict) is the *product* of the
  tool, not telemetry: it is written straight to the output stream and can
  never be swallowed by a log-level filter.

Colors: ANSI escapes, no third-party deps. Enabled only when the stream is
a real terminal ("auto"), overridable with --color always/never. The
NO_COLOR convention (https://no-color.org) is respected in auto mode.
"""

import logging
import os
import sys

from .models import MergeRequest
from .rules_engine import RuleResult

_RESET = "\033[0m"
_ANSI = {
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}


def _colors_enabled(mode: str, stream) -> bool:
    """Decide whether to emit ANSI colors for the given mode and stream."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    # auto: real terminal only, and the user hasn't opted out globally
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


class _ColorFormatter(logging.Formatter):
    """Colors diagnostic lines by severity: DEBUG dim, INFO cyan,
    WARNING yellow, ERROR red, CRITICAL bold red. The whole line is
    tinted so a wall of --verbose output is scannable at a glance."""

    _LEVEL_STYLES = {
        logging.DEBUG: _ANSI["dim"],
        logging.INFO: _ANSI["cyan"],
        logging.WARNING: _ANSI["yellow"],
        logging.ERROR: _ANSI["red"],
        logging.CRITICAL: _ANSI["red"] + _ANSI["bold"],
    }

    def __init__(self, enabled: bool):
        super().__init__(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S"
        )
        self._enabled = enabled

    def format(self, record: logging.LogRecord) -> str:
        """Format the record, tinting the whole line by its severity."""
        line = super().format(record)
        style = self._LEVEL_STYLES.get(record.levelno)
        if self._enabled and style:
            return f"{style}{line}{_RESET}"
        return line


class Logger:
    """Owns all program output: stderr diagnostics and the stdout CI summary."""

    def __init__(self, verbose: bool = False, stream=None, color: str = "auto"):
        self._stream = stream if stream is not None else sys.stdout
        self._color = _colors_enabled(color, self._stream)
        self._log = logging.getLogger("mr_validator")
        if not self._log.handlers:
            handler = logging.StreamHandler(sys.stderr)
            # stderr gets its own TTY detection: with stdout redirected to a
            # file, diagnostics on the terminal should still be colored.
            handler.setFormatter(_ColorFormatter(_colors_enabled(color, sys.stderr)))
            self._log.addHandler(handler)
        self._log.setLevel(logging.DEBUG if verbose else logging.WARNING)

    def _paint(self, text: str, *styles: str) -> str:
        """Wrap text in the given ANSI styles, or return it as-is when colors are off."""
        if not self._color or not styles:
            return text
        prefix = "".join(_ANSI[style_name] for style_name in styles)
        return f"{prefix}{text}{_RESET}"

    # --- diagnostics ------------------------------------------------------

    def debug(self, msg: str, *args) -> None:
        """Log a debug-level diagnostic (visible only with --verbose)."""
        self._log.debug(msg, *args)

    def info(self, msg: str, *args) -> None:
        """Log an info-level diagnostic (visible only with --verbose)."""
        self._log.info(msg, *args)

    def error(self, msg: str, *args) -> None:
        """Log an error diagnostic (always visible, on stderr)."""
        self._log.error(msg, *args)

    # --- CI summary -------------------------------------------------------

    def mr_header(self, merge_request: MergeRequest) -> None:
        """Print which MR is being validated, with its title and URL."""
        name = self._paint(f"{merge_request.project}!{merge_request.iid}", "bold")
        title = self._paint(f'"{merge_request.title}"', "bold")
        self._write(f"Validating {name} — {title}")
        if merge_request.web_url:
            self._write(self._paint(merge_request.web_url, "dim"))
        self._write("")

    def rule_result(self, result: RuleResult) -> None:
        """Print one rule's PASS/FAIL line plus its detail, if any."""
        if result.passed:
            status = self._paint("PASS", "green", "bold")
        else:
            status = self._paint("FAIL", "red", "bold")
        self._write(f"{status}  {result.name}")
        if result.detail:
            style = "yellow" if not result.passed else "dim"
            self._write(f"      {self._paint(result.detail, style)}")

    def verdict(self, results: list[RuleResult]) -> None:
        """Print the final PASS/FAIL verdict line summarizing all rules."""
        failed = sum(1 for result in results if not result.passed)
        self._write("")
        if failed:
            text = (
                f"RESULT: FAIL — {failed} of {len(results)} rules failed; "
                "this MR must not be merged yet"
            )
            self._write(self._paint(text, "red", "bold"))
        else:
            text = f"RESULT: PASS — all {len(results)} rules passed"
            self._write(self._paint(text, "green", "bold"))

    def _write(self, line: str) -> None:
        """Write one line to the summary output stream."""
        print(line, file=self._stream)
