#!/usr/bin/env python3
"""
Mock Jira server for the MR Pre-Merge Validator homework task.

Run with:
    python mock_jira.py

Serves on http://localhost:8080. Implements a minimal subset of the
Jira REST API v3:

    GET /rest/api/3/issue/{key}    ->  returns the issue or 404

Any bearer token is accepted for auth (the Authorization header is
ignored entirely; auth is not validated). Responses follow the real
Jira v3 response shape, so swapping the base URL to point at a real
Jira instance should be the only code change needed.

The seeded dataset includes WMS-* tickets across all workflow states
and issue types. See ISSUES below.
"""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = "localhost"
PORT = 8080


def _issue(key, summary, status, issuetype, assignee=None, priority="Medium",
           labels=None, fix_versions=None):
    """Build a Jira-shaped issue document."""
    # Jira's statusCategory groups workflow states; faithfully match the
    # shape real Jira uses so candidate code that drills into it works
    # against both.
    status_categories = {
        "Open":        ("new",           "To Do"),
        "In Progress": ("indeterminate", "In Progress"),
        "In Review":   ("indeterminate", "In Progress"),
        "Done":        ("done",          "Done"),
        "Won't Do":    ("done",          "Done"),
    }
    cat_key, cat_name = status_categories[status]
    numeric = key.split("-", 1)[1]
    return {
        "id": f"10{numeric}",
        "key": key,
        "self": f"http://{HOST}:{PORT}/rest/api/3/issue/{key}",
        "fields": {
            "summary": summary,
            "status": {
                "name": status,
                "statusCategory": {"key": cat_key, "name": cat_name},
            },
            "issuetype": {"name": issuetype},
            "assignee": (
                {
                    "displayName": assignee,
                    "accountId": assignee.lower().replace(" ", "."),
                }
                if assignee else None
            ),
            "priority": {"name": priority},
            "labels": labels or [],
            "fixVersions": [{"name": v} for v in (fix_versions or [])],
        },
    }


# Seeded dataset. Designed to exercise every rule in the homework:
#   - Rule 3 (ticket doesn't exist):       use any unlisted key, e.g. WMS-9999
#   - Rule 4 (ticket in wrong state):      WMS-1010..1012, WMS-1100
#   - Passing tickets (In Review / Done):  WMS-1001..1004, WMS-1020, WMS-1101
ISSUES = {
    i["key"]: i for i in [
        # --- Tickets that PASS the state check (In Review / Done / Won't Do) ---
        _issue("WMS-1001", "Add bearer-token auth to the inventory API",
               "In Review", "Story",
               assignee="Alice Smith", priority="High",
               labels=["backend", "auth"], fix_versions=["2026.05"]),

        _issue("WMS-1002", "Fix race condition in shipment dispatcher",
               "In Review", "Bug",
               assignee="Bob Chen", priority="High",
               fix_versions=["2026.05"]),

        _issue("WMS-1003", "Bump third-party barcode SDK to v3.2",
               "Done", "Task",
               assignee="Carol Diaz", priority="Medium",
               fix_versions=["2026.04"]),

        _issue("WMS-1004", "Add pagination to the inventory list endpoint",
               "Done", "Story",
               assignee="Alice Smith", priority="Medium",
               fix_versions=["2026.04"]),

        _issue("WMS-1020", "Migrate legacy reporting format to new CSV exporter",
               "Won't Do", "Task",
               assignee="Alice Smith", priority="Low"),

        _issue("WMS-1101", "Update DB schema for shelving metadata",
               "In Review", "Sub-task",
               assignee="Bob Chen", priority="Medium",
               fix_versions=["2026.05"]),

        # --- Tickets that FAIL the state check (Open / In Progress) ---
        _issue("WMS-1010", "Refactor the warehouse picking algorithm",
               "In Progress", "Story",
               assignee="Bob Chen", priority="Medium",
               fix_versions=["2026.06"]),

        _issue("WMS-1011", "Investigate missing-notification reports from EU customers",
               "Open", "Bug",
               assignee=None, priority="Low"),

        _issue("WMS-1012", "Design new operator dashboard layout",
               "In Progress", "Task",
               assignee="Carol Diaz", priority="Low",
               fix_versions=["2026.06"]),

        _issue("WMS-1100", "Q2 Warehouse Modernization",
               "In Progress", "Epic",
               assignee="Dana Park", priority="High",
               fix_versions=["2026.05", "2026.06"]),
    ]
}


ISSUE_PATH_RE = re.compile(r"^/rest/api/3/issue/([A-Z][A-Z0-9]*-\d+)/?$")


class MockJiraHandler(BaseHTTPRequestHandler):
    server_version = "MockJira/1.0"

    def do_GET(self):
        match = ISSUE_PATH_RE.match(self.path)
        if match:
            self._handle_issue(match.group(1))
            return
        self._send_json(404, {
            "errorMessages": [f"No handler for path: {self.path}"],
            "errors": {},
        })

    def _handle_issue(self, key):
        issue = ISSUES.get(key)
        if issue is None:
            # Match real Jira's 404 body shape so candidate error handling
            # has something realistic to parse.
            self._send_json(404, {
                "errorMessages": [
                    "Issue does not exist or you do not have permission to see it."
                ],
                "errors": {},
            })
            return
        self._send_json(200, issue)

    def _send_json(self, status, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[mock-jira] {self.address_string()} - {fmt % args}\n")


def main():
    print(f"Mock Jira running on http://{HOST}:{PORT}")
    print(f"Seeded issues ({len(ISSUES)}):")
    for key in sorted(ISSUES.keys()):
        status = ISSUES[key]["fields"]["status"]["name"]
        itype = ISSUES[key]["fields"]["issuetype"]["name"]
        print(f"  {key}  [{status:<11}]  {itype:<8}  {ISSUES[key]['fields']['summary']}")
    print()
    print("Try:")
    print(f"  curl http://{HOST}:{PORT}/rest/api/3/issue/WMS-1001")
    print(f"  curl http://{HOST}:{PORT}/rest/api/3/issue/WMS-9999    # 404")
    print()
    httpd = HTTPServer((HOST, PORT), MockJiraHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.server_close()


if __name__ == "__main__":
    main()
