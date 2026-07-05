# mr-validator

A pre-merge gate for CI: given a GitLab merge request, it checks that the MR
references Jira tickets and that those tickets are in a mergeable state.
Exit code 0 means the MR may be merged; non-zero blocks it. The printed
summary tells the developer exactly which rule failed and what to do next.

## The rules

An MR **fails** the gate (exit 1) if any of these are true:

1. The MR is in **Draft** state.
2. The MR references **zero** Jira tickets. References are searched in the
   MR title, source branch name, description, and all commit messages.
3. A referenced ticket **does not exist** in Jira.
4. Any referenced ticket is **not** in state `In Review` or `Done`
   (so `Open`, `In Progress` and `Won't Do` all block the merge).

All four rules are always evaluated — the summary shows every problem at
once, not just the first one.

## Getting started

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs the runtime dependency (`requests`), the test tooling
(`pytest`), and the `mr-validator` command itself.

## Running it

Start the provided mock Jira in another terminal (the tool talks to
`http://localhost:8080` by default):

```bash
python mock_jira.py
```

Then validate an MR, either by URL or by IID + project:

```bash
mr-validator https://gitlab.com/sztomi/mr-validator-homework/-/merge_requests/1
mr-validator 1 --project sztomi/mr-validator-homework
```

A passing run:

```
Validating sztomi/mr-validator-homework!1 — "WMS-1001: Add bearer-token auth to inventory API"
https://gitlab.com/sztomi/mr-validator-homework/-/merge_requests/1

PASS  MR is not a draft
PASS  MR references at least one Jira ticket
      WMS-1001 (found in: title, branch, description, commits)
PASS  All referenced tickets exist in Jira
PASS  All referenced tickets are in an accepted state
      WMS-1001 is 'In Review'

RESULT: PASS — all 4 rules passed
```

A failing run (one ticket of two is still In Progress):

```
Validating sztomi/mr-validator-homework!12 — "WMS-1001, WMS-1010: combined work"
https://gitlab.com/sztomi/mr-validator-homework/-/merge_requests/12

PASS  MR is not a draft
PASS  MR references at least one Jira ticket
      WMS-1001 (found in: title, branch, description, commits), WMS-1010 (found in: title, description, commits)
PASS  All referenced tickets exist in Jira
FAIL  All referenced tickets are in an accepted state
      WMS-1010 is 'In Progress'; tickets must be Done or In Review before merging

RESULT: FAIL — 1 of 4 rules failed; this MR must not be merged yet
```

## Configuration

Every option is a flag with an environment-variable fallback, so CI can
configure the tool without changing the command line:

| Flag             | Env var                     | Default                 |
|------------------|-----------------------------|-------------------------|
| `--gitlab-url`   | `MR_VALIDATOR_GITLAB_URL`   | `https://gitlab.com`    |
| `--gitlab-token` | `MR_VALIDATOR_GITLAB_TOKEN` | none (public read)      |
| `--jira-url`     | `MR_VALIDATOR_JIRA_URL`     | `http://localhost:8080` |
| `--jira-token`   | `MR_VALIDATOR_JIRA_TOKEN`   | none                    |

`-v/--verbose` prints diagnostics (HTTP calls, timings, per-ticket lookups)
to stderr. `--color auto|always|never` controls the summary colors; `auto`
colors only real terminals and respects `NO_COLOR`.

## Exit codes

| Code | Meaning                                                        |
|------|----------------------------------------------------------------|
| 0    | All rules passed — the MR may be merged                        |
| 1    | At least one rule failed — the MR must not be merged           |
| 2    | The validator itself could not do its job (bad arguments, network trouble, MR not found) |

The 1/2 split matters in CI: a red gate caused by a network hiccup (2)
should not read as "this MR is invalid" (1).

## Tests

```bash
pytest              # everything: 54 unit + 18 end-to-end
pytest -m "not e2e" # unit tests only, no network needed
```

The end-to-end tests run the real CLI as a subprocess against the public
fixture project on gitlab.com, with `mock_jira.py` spawned automatically on
a free port — every fixture MR is asserted against its expected exit code
and summary output.

## Design notes

- **stdout is the product, stderr is telemetry.** The summary goes to
  stdout and is never filtered; diagnostics go through stdlib `logging` to
  stderr, gated by `--verbose`. Piping the summary to a file keeps it clean.
- **References are a union, not a priority list.** A ticket mentioned only
  in a commit message is still validated — with priority semantics, a bad
  ticket hiding in the branch name would be silently ignored, which is the
  unsafe direction for a gate.
- **A missing Jira ticket is data, not an error.** Jira 404 → rule 3 fails
  (exit 1). A missing *MR* is different: there is nothing to validate, so
  that is a configuration error (exit 2).
- **Ticket keys inside markdown code blocks don't count.** A `WMS-1234` in
  a code example is not a reference to work being merged.

## What it doesn't do

- The ticket pattern (`WMS-\d+`) and the accepted states are constants in
  the code, not configuration — fine for one team's convention, would need
  a config file to serve several.
- Jira lookups are sequential; an MR referencing dozens of tickets would be
  slower than necessary.
- No retries/backoff on flaky networks — a transient failure exits 2 and CI
  retries the job instead.
- It reads GitLab only; it does not post the result back as an MR comment.
