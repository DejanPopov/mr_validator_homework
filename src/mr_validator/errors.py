"""Exceptions shared across the package."""


class ApiError(Exception):
    """A GitLab or Jira call failed for a reason unrelated to the MR itself.

    Network trouble, timeouts, unexpected HTTP statuses, bad configuration.
    The CLI maps this to exit code 2 so CI can tell "the MR is invalid"
    (exit 1) apart from "the validator could not do its job" (exit 2).
    """
