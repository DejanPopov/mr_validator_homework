# mini — the one-day version

If this task had to be done within one day, this is what I would ship:
one file, ~100 lines, standard library only. It is kept next to the real
tool as a working answer to the question *"why isn't this just a script?"*

## Run it

No install, no venv — bare `python3` is enough:

```sh
# terminal 1: the provided mock Jira
python3 ../mock_jira.py

# terminal 2
python3 mini_validator.py https://gitlab.com/sztomi/mr-validator-homework/-/merge_requests/1
```

Same env vars as the real tool: `MR_VALIDATOR_JIRA_URL` (default
`http://localhost:8080`), `MR_VALIDATOR_GITLAB_TOKEN`, `MR_VALIDATOR_JIRA_TOKEN`.

## What it gets right

Scored against the same 13 fixture MRs the e2e suite uses as the
acceptance spec: **12 of 13 verdicts correct.** All four rules work:
draft check, at-least-one-ticket, tickets exist in Jira, tickets in an
accepted state ('In Review' / 'Done').

## What it gets wrong — measured, not guessed

- **MR !13 is a false pass.** The ticket key appears only inside a
  markdown code block; the naive regex counts it, and since that ticket
  is 'In Review' the gate approves an MR it should block. The real tool
  strips code blocks before matching (`extractor._strip_code`).
- **An outage is reported as a bad MR.** When Jira is unreachable this
  script dies with a traceback and exit code 1 — the same exit code as
  "the MR failed a rule", so CI blames the developer for an
  infrastructure problem. The real tool separates the two: exit 1 means
  *verdict: don't merge*, exit 2 means *I could not do my job*.
- **Only the first commit page is fetched.** GitLab returns 20 commits
  per page; a ticket referenced only in commit #21 is silently missed.
  The real tool paginates.
- **No tests.** The script has no seams to test against — you verify it
  by running it against live GitLab, which is exactly how the false
  pass above was found.

## The point

The real tool is ~4x this size. The difference is not abstraction —
it is the four bullets above, each of which is a wrong merge decision
or a lying exit code. That is what a day of extra work buys.
