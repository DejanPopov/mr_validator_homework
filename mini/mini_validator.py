#!/usr/bin/env python3
"""mini_validator.py — the whole MR pre-merge gate as one naive script.

NOT the submission (git-excluded). A deliberately simple version of
mr-validator, written to see what the structured version actually buys.
Corners cut on purpose:

  - ticket keys inside markdown code blocks still count (no stripping)
  - only the first page of commits is fetched (GitLab returns 20 by default)
  - any network/API problem is an unhandled traceback -> exit 1, which CI
    cannot tell apart from "the MR failed a rule"
  - no tests, no logging, no color

Stdlib only — runs on bare python3, nothing to install.

Usage:
    python3 mini_validator.py https://gitlab.com/<project>/-/merge_requests/<iid>

Env (same names as the real tool):
    MR_VALIDATOR_JIRA_URL      (default http://localhost:8080)
    MR_VALIDATOR_GITLAB_TOKEN  (optional, private projects only)
    MR_VALIDATOR_JIRA_TOKEN    (optional)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

JIRA_URL = os.environ.get("MR_VALIDATOR_JIRA_URL", "http://localhost:8080").rstrip("/")
ACCEPTED_STATES = ("In Review", "Done")
TICKET_RE = re.compile(r"(?<![A-Za-z0-9])WMS-\d+(?!\d)")


def get_json(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def gitlab_get(url):
    headers = {}
    if token := os.environ.get("MR_VALIDATOR_GITLAB_TOKEN"):
        headers["PRIVATE-TOKEN"] = token
    return get_json(url, headers)


def fetch_ticket(key):
    headers = {}
    if token := os.environ.get("MR_VALIDATOR_JIRA_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        return get_json(f"{JIRA_URL}/rest/api/3/issue/{key}", headers)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python mini_validator.py <merge request URL>")
    match = re.match(r"(https?://[^/]+)/(.+?)/-/merge_requests/(\d+)/?$", sys.argv[1])
    if not match:
        sys.exit(f"not a merge request URL: {sys.argv[1]!r}")
    base, project, iid = match.groups()
    api = f"{base}/api/v4/projects/{quote(project, safe='')}/merge_requests/{iid}"

    mr = gitlab_get(api)
    commits = gitlab_get(f"{api}/commits")  # first page only!

    text = "\n".join(
        [mr["title"], mr["source_branch"], mr.get("description") or ""]
        + [commit["message"] for commit in commits]
    )
    keys = sorted(set(TICKET_RE.findall(text)))
    states = {}
    for key in keys:
        ticket = fetch_ticket(key)
        states[key] = ticket["fields"]["status"]["name"] if ticket else None

    failures = []
    if mr.get("draft"):
        failures.append("MR is marked as Draft")
    if not keys:
        failures.append("no WMS-* ticket referenced in title/branch/description/commits")
    if missing := [key for key, state in states.items() if state is None]:
        failures.append(f"not found in Jira: {', '.join(missing)}")
    if wrong := [f"{k} is {s!r}" for k, s in states.items() if s and s not in ACCEPTED_STATES]:
        failures.append(f"wrong state: {', '.join(wrong)} (need In Review or Done)")

    print(f"MR !{iid}: {mr['title']}")
    for key, state in states.items():
        print(f"  {key}: {state or 'NOT FOUND'}")
    for failure in failures:
        print(f"  FAIL: {failure}")
    print("RESULT:", "FAIL" if failures else "PASS")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
