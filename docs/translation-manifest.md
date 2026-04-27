# Translation manifest

State of every artifact that participates in the en ↔ ja translation pipeline.

## Legend

| State | Meaning |
|---|---|
| `translated` | en file is a translation of an explicit ja source; cross-linked in headers. |
| `copied` | en file is byte-equivalent to ja source (e.g., LICENSE, schema JSON). |
| `intentionally omitted` | ja artifact has no en counterpart (e.g., `registry/projects.md`). |
| `local-only` | en file has no ja counterpart (e.g., `bootstrap-cherry-picks.md`). |

## Rows

(Filled in by Wave B-core, Wave B-runtime, Wave C as files are translated.)

| en path | state | source ja path / sha | last sync sha | notes |
|---|---|---|---|---|

## Wave assignment

- Wave B-core fills rows for: README, CLAUDE.md, role docs, overviews, non-goals, getting-started, oss-comparison, org-state-schema.
- Wave B-runtime fills rows for: install / dashboard / tools / all 10 skills / testing / verification / knowledge/curated.
- Wave C closes the manifest by ensuring every en file has either a row here or is referenced in `canonical-ownership.md` as en-canonical.
