# Automated Tests

Run guide bundling the Python-based parser/converter regression tests and the
Bash-based hook regression tests.

## Coverage

| Function | Description |
|------|------|
| `_parse_org_state` | Parses org-state.md status, purpose, and work items |
| `_parse_journal` | Parses the journal.jsonl event log |
| `_parse_projects` | Parses the markdown table in projects.md |
| `_parse_workers` | Parses the worker-*.md files |
| `_parse_knowledge` | Counts H2 sections in curated/*.md |
| `org_state_converter.py` | org-state Markdown → JSON conversion and dashboard JSON loading |
| `.hooks/*.sh` | Worker boundary / claude-org structure / git push block regression detection |

## How to run

```bash
# Python tests
# Windows (use python if py -3 is unavailable)
python -m unittest discover -s tests -v

# Mac / Linux
python3 -m unittest discover -s tests -v

# Shell hook tests
bash tests/run-all.sh
```

Run from the project root. No external libraries are required, but the shell
hook tests need `bash` and `jq`.

In daily operation, treat success as "Python tests AND `bash tests/run-all.sh`
both pass," not just the Python tests.

## Test layout

```
tests/
  __init__.py              # Package init (empty)
  test_parsers.py          # Parser tests for dashboard/server.py
  test_org_state_converter.py
  run-all.sh               # Shell hook test runner
  test-block-git-push.sh
  test-block-org-structure.sh
  test-check-worker-boundary.sh
  fixtures/
    org-state-sample.md    # Sample for the org-state parser
    journal-sample.jsonl   # Sample for the journal parser
    projects-sample.md     # Sample for the projects parser
    workers/
      worker-abc12345.md   # Sample for the workers parser
    curated/
      .gitkeep             # Used to verify skip behavior
      sample-topic.md      # Sample for the knowledge parser
```

## Saving test results

When recording test results, save them under `docs/test-results/`.

## CI

GitHub Actions runs the same two test suites. To reduce failures that cannot
be reproduced locally, run both suites before opening a PR.
