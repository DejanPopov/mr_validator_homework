"""The shared output helper for CLI tools; knows nothing about mr-validator.

A tool's entry point instantiates Logger once. That installs the handler,
level, and colors on the tool's root stdlib logger — every module that
logs via plain logging.getLogger(__name__) inherits them automatically,
because records propagate up the logging hierarchy. The instance also
owns the tool's product output stream (write/paint).

Two channels, deliberately separate:

- diagnostics (debug/info/error) go through stdlib logging to stderr;
  verbose=True turns the chatty levels on.
- product output (write, styled with paint) is written straight to the
  output stream and can never be swallowed by a log-level filter.

Colors: ANSI escapes, no third-party deps. Enabled only when the stream is
a real terminal ("auto"), overridable with color="always"/"never". The
NO_COLOR convention (https://no-color.org) is respected in auto mode.
"""

import logging
import os
import sys

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
    tinted so a wall of verbose output is scannable at a glance."""

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
    """Owns a program's output: stderr diagnostics and a stdout product stream.

    `name` is the root of the stdlib logging hierarchy to configure —
    typically the tool's package name, so every module underneath it
    logging via logging.getLogger(__name__) is covered.
    """

    def __init__(
        self, name: str, verbose: bool = False, stream=None, color: str = "auto"
    ):
        self._stream = stream if stream is not None else sys.stdout
        self._color = _colors_enabled(color, self._stream)
        self._log = logging.getLogger(name)
        if not self._log.handlers:
            handler = logging.StreamHandler(sys.stderr)
            # stderr gets its own TTY detection: with stdout redirected to a
            # file, diagnostics on the terminal should still be colored.
            handler.setFormatter(_ColorFormatter(_colors_enabled(color, sys.stderr)))
            self._log.addHandler(handler)
        self._log.setLevel(logging.DEBUG if verbose else logging.WARNING)

    # --- diagnostics ------------------------------------------------------

    def debug(self, msg: str, *args) -> None:
        """Log a debug-level diagnostic (visible only when verbose)."""
        self._log.debug(msg, *args)

    def info(self, msg: str, *args) -> None:
        """Log an info-level diagnostic (visible only when verbose)."""
        self._log.info(msg, *args)

    def error(self, msg: str, *args) -> None:
        """Log an error diagnostic (always visible, on stderr)."""
        self._log.error(msg, *args)

    # --- product output ---------------------------------------------------

    def paint(self, text: str, *styles: str) -> str:
        """Wrap text in the given ANSI styles, or return it as-is when colors are off."""
        if not self._color or not styles:
            return text
        prefix = "".join(_ANSI[style_name] for style_name in styles)
        return f"{prefix}{text}{_RESET}"

    def write(self, line: str) -> None:
        """Write one line to the product output stream."""
        print(line, file=self._stream)
