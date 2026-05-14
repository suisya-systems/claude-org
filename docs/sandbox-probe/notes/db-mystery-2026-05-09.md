# Audit of the temporary `.state/state.db` 0-row visibility incident (Issue #376 Iteration A side effect)

> **【Correction 2026-05-09 later】** The hypothesis A (sandbox shadow FS) that the initial version of this audit (commit `4864af5`) rated as "leading" is **rejected**. Immediately after the push of PR #385, the Secretary re-observed the same `runs=0` phenomenon and discovered on the real machine that, due to the cwd drifting into the audit worktree (`.worktrees/db-mystery-iter-a-audit/`), running `python -c "sqlite3.connect('.state/state.db')..."` etc. was simply reading a **separately created `.state/state.db` inside the worktree (inode 615758, runs=0)**. The real DB (`<claude-org-root>/.state/state.db`, inode 621604) was always at runs=13 and healthy.
>
> The true cause is **hypothesis D (two DB file confusion)**, and the mechanism is that the **state_db-related tools resolve `.state/state.db` relative to cwd**. See **§7 Root cause and recurrence prevention proposals** at the end of this document for details.
>
> The initial body (§1–§6) below §0 is **preserved as-is** (it has value as a work log of the audit and as an example of "hypothesis evaluation being overturned by real-machine verification"). A `→ Correction:` marker is appended to each hypothesis-evaluation block to make the gap between the initial judgment and the corrected judgment explicit.

## 0. Position of this document

This is an audit of the event where, during Iteration A B1-1 probe (from 2026-05-09 09:42 UTC onwards), SELECTs issued by the Secretary against `.state/state.db` temporarily returned **0 rows in the `runs` table**.

- Mode: **observation / hypothesis organization only**. No code changes. No write experiments against the production `.state/state.db` either.
- worktree: `audit/db-mystery-iter-a` (this worktree does not hold `.state/state.db`).
- Verification was done using (a) static code reading and (b) **read-only** PRAGMA / count observations on a separate worktree (`<claude-org-root>/.state/state.db`).
- Corrective actions derived from the primary-SoT of this audit are handled in separate issues / PRs (this document is plausibility evaluation of the cause hypotheses only).

The worker did not run the probe. The Secretary + user were running the iteration A B1-1 probe on the dispatcher pane, and the 1-sample incidentally observed during that process is transcribed.

## 1. Observed event (timeline)

(Below is a copy from CLAUDE.local.md + normalization by the worker. Times are all UTC ≈ JST -9h; state retrieval is read-only.)

| time | action | observation |
|---|---|---|
| 09:32 | Session start, Secretary `get_resume_briefing` | DB: runs=9 (completed), events=60+, projects=4, worker_dirs=4, session.status=SUSPENDED |
| 09:42–09:55 | Iteration A B1-1 probe run by Secretary + user on dispatcher pane | dispatcher's sandbox switched **No Sandbox → auto-allow** |
| ~10:00 | dispatcher received DELEGATE (writeup task), attempted DB write via `tools/journal_append.sh` while sandbox active | "**unable to open database file**" error. Got by with a fallback updating worker state.md directly via the Write tool |
| ~10:25 | sandbox-probe-iter-a-b1-1-writeup worker complete | Secretary ran `update_run_status('...writeup', 'review')`, displayed success |
| ~10:30 | sandbox-probe-iter-a-incorporate worker complete | Secretary ran `update_run_status('...incorporate', 'review')`, displayed success |
| 10:38 | Right after Secretary ran `gh pr create` to create PR #384 + `journal_append.sh pr_opened` | `python -c "SELECT count(*) FROM runs"` returns **0**. projects=0, events=1, **session.status=IDLE**. `runs WHERE task_id LIKE '%iter-a%'` also 0 hits |
| ~10:40 | Secretary restored session via SQL UPDATE + re-INSERTed 2 runs | classifier refused → user approved → restoration executed → displayed success |
| ~10:45 | `gh pr merge 384` → `run_complete_on_merge.py` → `git pull --ff-only origin main` → SELECT runs | 12 rows of runs (9 history + abandoned + writeup completed + incorporate completed) are **visible again** |

Characteristics of the 10:38 observation (the core of this mystery):

- runs=0
- projects=0
- events=1 (= presumed to be the one row inserted by the immediately preceding `journal_append.sh pr_opened`)
- session.status=**IDLE** (= transitioned from existing SUSPENDED to "initial value")
- WAL / SHM file state not captured

10:45 observation (after recovery):

- runs=12 (the integer matches independently of the operator's SQL UPDATE / INSERT intervention)
- session.status=SUSPENDED (back to original)

Real production DB observations at the time of writing (later on 2026-05-09; read-only PRAGMA / count done by the audit):

```text
journal_mode = wal
synchronous  = 2 (FULL)
locking_mode = normal
runs    : 13
events  : 67
projects: 4
session.status = SUSPENDED
schema_migrations: [v1 'M0: initial schema (Issue #267)', v2 'M2: org_sessions singleton (Issue #267)']
.state/state.db-wal / .db-shm : absent (= all connections closed + checkpoint clean)
.state/state.db inode = 621604 (single file, no other state.db copies in repo tree)
```

That is, the final DB's physical state is healthy. At the time of this writing, it is fixed that the 10:38 observation was **not permanent DB corruption but a temporary visibility anomaly**.

## 2. Static investigation of code paths (audit scope)

The main paths needed for hypothesis evaluation (with reference symbols, used below in §3):

### 2.1 Connection / WAL mode

[`connect`](../../../tools/state_db/__init__.py) of [`tools/state_db/__init__.py`](../../../tools/state_db/__init__.py) issues `PRAGMA journal_mode = WAL` each time it connects (excluding `:memory:`).

```python
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA busy_timeout = 5000")
if db_path != ":memory:":
    conn.execute("PRAGMA journal_mode = WAL")
```

→ Fixed that the production DB is WAL-operated (also observed `wal` via `pragma journal_mode`).

### 2.2 Schema auto-initialization and the origin of "IDLE"

`_db_append` of [`tools/journal_append.py`](../../../tools/journal_append.py) automatically creates a fresh DB and applies schema when the DB file does not exist:

```python
db_path = repo_root / ".state" / "state.db"
db_path.parent.mkdir(parents=True, exist_ok=True)
is_new_db = not db_path.exists()
conn = connect(db_path)
try:
    if is_new_db:
        apply_schema(conn)
    writer = StateWriter(conn)            # ↓ ensure_m2_schema runs here
    writer.append_event(kind=event, ...)
    writer.commit()
```

`StateWriter.__init__` calls [`ensure_m2_schema`](../../../tools/state_db/__init__.py). `ensure_m2_schema` seeds the `org_sessions` singleton row with `INSERT OR IGNORE`:

```sql
INSERT OR IGNORE INTO org_sessions (id, status, last_writer_at)
VALUES (1, 'IDLE', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
```

In other words, the DB shape "immediately after `journal_append.py` runs once against a fresh DB" is:

- `runs` = 0
- `projects` = 0
- `events` = 1 (just the one row appended now)
- `org_sessions.id=1, status='IDLE'`

— **perfectly matching the shape observed at 10:38**.

Additionally, `StateWriter.commit()` regenerates `.state/org-state.md` via [`tools.state_db.snapshotter.post_commit_regenerate`](../../../tools/state_db/snapshotter.py) and `.state/org-state.json` via [`dashboard.org_state_converter.convert`](../../../dashboard/org_state_converter.py) at the post-commit hook, both from DB-derived sources. With a fresh DB committed, the regenerated contents also become "empty + IDLE" equivalent.

### 2.3 DROP TABLE path via importer

`_reset_schema` of [`tools/state_db/importer.py`](../../../tools/state_db/importer.py) **DROPs all tables** + re-applies `apply_schema`. `import_full_rebuild` only runs via an explicit path with the `--rebuild` flag (in `_main`, absence of `--rebuild` results in `error` exit 2, lines 696-699).

The SKILL.md of `org-start` / `org-resume` / `org-suspend` / `org-delegate` each say "if DB is absent, build via `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`", but that is **manual operator execution**; no automatic / hook-driven rebuild was found in this repository (grep-confirmed under .git/hooks, .claude/hooks, .hooks/ — no hook calling `state.db` / `importer` **exists**).

### 2.4 DB file path resolution method

> **→ Correction (2026-05-09 later)**: this section's conclusion of "cwd-independent" is **incorrect**. `__file__`-based resolution **does not directly read cwd within the same worker / same cwd in which the script is started**, but **in environments with multiple worktrees, which worktree's script is launched is determined by cwd**, so as a result `<worktree>/.state/state.db` is selected. Furthermore, ad-hoc `python -c "sqlite3.connect('.state/state.db')..."` is **purely cwd-relative**. See §7.1 / §7.3 of this document. The findings below are **preserved as-is in the initial body**.

- `tools/journal_append.sh`: computes `SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); REPO_ROOT="$SCRIPT_DIR/.."` and then **`cd "$REPO_ROOT"`** before exec-ing python. cwd-independent. ← **【Correction: the script's location = worktree is determined by cwd, so consequently cwd-dependent】**
- `tools/journal_append.py`: `_REPO_ROOT = Path(__file__).resolve().parent.parent`. Also cwd-independent. ← **【Correction: same as above】**
- `tools/gen_delegate_payload.py:836`: `claude_org_root / ".state" / "state.db"` (root is passed via option resolution).
- `dashboard/org_state_converter.py:25`: `BASE_DIR = Path(__file__).parent.parent` → `.state/state.db`. cwd-independent. ← **【Correction: same as above; the worktree is determined via the startup path】**
- `dashboard/server.py:54`: same as above.
- In this audit's grep, all `state.db` / `state_db` path resolutions are **`__file__`-based**; no cwd-based relative resolutions were found. ← **【Correction: ad-hoc Python one-liners (`python -c "..."`) are fully cwd-relative, so a cwd-dependent path exists on an axis separate from in-tool path resolution】**

→ Therefore, the line "dispatcher resolves `.state/state.db` relatively while staying at cwd `.dispatcher/` and opens a different file `.dispatcher/.state/state.db`" **does not exist as a code path**. The literal version of hypothesis D can be rejected statically.

However, the possibility that **the same absolute path** appears as different contents due to sandbox bind-mount composition remains (this is option A's territory).

### 2.5 Relation between dispatcher cwd and DB absolute path

The dispatcher's cwd is `.dispatcher/`, but `tools/journal_append.sh` `cd $REPO_ROOT` before invoking python, canceling cwd. The actual dispatcher reaches the DB via the **absolute path** `<repo_root>/.state/state.db`.

`.dispatcher/references/worker-monitoring.md:503` has a one-liner example `sqlite3 ../.state/state.db ...`. That is a read-only query example for dispatcher Claude direct execution, ascending `..` to repo root from dispatcher cwd `.dispatcher/`. Resolves to absolute-path-equivalent (`.dispatcher/..` = repo root).

## 3. Evaluation of hypotheses A–E

### 3.1 Hypothesis A: overwrite by sandbox auto-allow shadow FS

> **→ Correction (2026-05-09 later): rejected**. On real-machine reproduction by the Secretary right after the PR #385 push, the observed `runs=0` phenomenon was found to be **opening a different DB due to cwd drift**, independent of the sandbox layer (details: §7 / opening correction note of this document). This hypothesis was rated "complete match with mechanical explanation" at the end of this block in the initial version, but that was a **superficial similarity with the fresh DB shape**, and is wrong as a cause path. Hypothesis A retains value as further investigation of sandbox semantics, but is not the true cause of this db-mystery. The evaluation block below is **preserved as-is from the initial body** (for its tracing value as faulty reasoning).

> When dispatcher / Secretary's sandbox is auto-allow, writes to `.state/state.db` deviated into the bubblewrap shadow FS; later, the shadow was visible at the moment the real path was read; or via the shadow, an empty DB was written back to the real path.

**Evaluation: high plausibility (leading at this time)** ← **【Rejected by correction. See note above】**

Grounds:

- The 10:38 observation shape (`runs=0, projects=0, events=1, session.status=IDLE`) is in **complete agreement** with §2.2's "immediately after `journal_append.py` runs once against a fresh DB". `status=IDLE` is the value explicitly seeded as the SQL literal `'IDLE'`, so accidental generation is unlikely.
- The path from 10:00 dispatcher's "unable to open database file" failure → 10:38 Secretary's IDLE observation = "**under the same sandbox semantics, transitioned to a path of 'open fails → exists() false → fresh DB creation'**" goes through smoothly (the diff between 10:00 and 10:38 is whether the sandbox layer's bind-mount state changed over time, or whether tmpfs-ification happened only on Secretary side).
- The recovery at 10:45 with "runs=12 visible again" means **not permanent destruction but a view-level anomaly**. The behavior of overlay/tmpfs in bubblewrap etc. — where view disappears on child process exit (or transition outside the sandbox boundary) — matches.

Rejection conditions (= observations that reject this hypothesis):

- If `cat /proc/self/mountinfo` etc. confirms that bubblewrap does not lay shadow / tmpfs over `.state/` (= the bind-mount composition has `.state/` as RW pass-through to the real FS).
- If 10:40 Secretary's manual `INSERT INTO runs ...` 2 rows are confirmed to be **definitely persisted to the production DB side** (= updated the real view, not the shadow). (If it were writes to shadow, 10:45 would not be 12; should be 10 or so — needs distinguishing whether 12 is original 9 history + 2 review (write) + 1 abandoned etc., or 9 + 1 abandoned + 2 (writeup/incorporate completed by 10:25/10:30 update)).

Verification means (next iteration):

- In parallel with B1-1, add **probe row 1.6** (proposed in §5.1) as "fire `tools/journal_append.sh` on real machine while sandbox auto-allow is active, and capture before/after `.state/state.db` inode and count inside / outside the sandbox respectively".
- Add bwrap startup mountinfo observation to the runbook.

### 3.2 Hypothesis B: SQLite WAL / journal mode mismatch

> Concurrent multi-process access checkpoint timing in WAL mode causes temporary "appears empty" possibility

**Evaluation: low plausibility (rejection-leaning)**

Grounds:

- WAL mode itself is confirmed (verified by PRAGMA: `journal_mode = wal`; this matches the literal inside connect() at the time of writing).
- However, WAL does not typically behave like "committed rows temporarily disappear". WAL semantics is "readers see WAL frames and observe up to the most recent commit"; "only checkpointed frames are reflected in the main DB file". Even if a new connection fails to read WAL, **existing rows in the main DB file appearing to be missing is spec-impossibly**.
- Even in the case of "connection read only main DB and ignored WAL", historical 9 runs should already be checkpointed into the main DB rather than WAL, so cannot become 0 rows.
- The observation shape `events=1, session.status=IDLE` cannot be explained by WAL bug (no path for why only 1 row survives and status changes to the `IDLE` literal).

Rejection conditions (= observations keeping this hypothesis alive):

- If the rare bug of "during WAL checkpoint, the `-shm` file corrupts and the reader sees the empty main DB" can be reproduced via the official sqlite issue tracker etc. (no such case is currently known).
- If logs from the 10:38 observation confirm that `state.db-wal` / `state.db-shm` were "abnormally large / absent / corrupted" (this observation did not capture WAL file state at the time).

In total, explaining the observed shape with WAL alone is difficult. **Keep only as accomplice to hypothesis A** (the story "inside sandbox shadow FS the WAL files split, and the reader saw only the empty main DB" is a subcase of A).

### 3.3 Hypothesis C: implicit rebuild by importer / other tools

> Possibility that StateWriter post-commit hook or dashboard.org_state_converter / snapshotter regenerated the DB from another source and emptied it

**Evaluation: low plausibility (rejected)**

Grounds:

- As confirmed in §2.3, `_reset_schema()` only starts **with the `--rebuild` flag from `import_full_rebuild`**. The timeline in CLAUDE.local.md does not include records of the operator running `python -m tools.state_db.importer --rebuild` around 10:38.
- `tools.state_db.snapshotter.post_commit_regenerate` is a **one-way dump from DB → markdown / JSON**, just reading the DB and overwriting. No path to rebuild DB from markdown / JSON exists across this repository (removed in M4 cutover, lines 10-13 in `dashboard/org_state_converter.py` "the pre-M4 ``--source markdown`` mode has been removed").
- No path for post-commit to erase the DB's `runs`. post-commit only issues read-only SELECTs (snapshotter's `_fetch_runs` etc.).

Rejection conditions (= observations keeping this hypothesis alive):

- If a rebuild path being missed at this time of writing is identified (e.g. individual operator shell alias / .bashrc etc.). Negative within the grep-checked range.

### 3.4 Hypothesis D: two DB file confusion

> **→ Correction (2026-05-09 later): adopted as the true cause**. The initial version's "literal version is rejected" was based on a verification that **`find` was only inside the audit worktree itself**, missing the **separately created `.state/state.db` under worktrees due to cwd drift by worker or Secretary**. Real-machine verification confirmed the existence of `.state/state.db` (inode 615758, 151552 bytes) inside the worktree (during Secretary's reproduction at around 11:18 on 2026-05-09). Details and recurrence prevention in §7. The evaluation block below is **preserved as-is from the initial body**.

> Confusion between `.state/state.db` and `.dispatcher/.state/...`

**Evaluation: medium plausibility (literal version rejected, effective version is a rephrasing of A)** ← **【Correction: the literal version is the true cause. The verification range was too narrow】**

Grounds:

- As in §2.4, code in this repository resolves `state.db` references via **all `__file__`-based absolute paths**. There is no **literal path-confusion path** like "dispatcher resolves relative `.state/state.db` from cwd `.dispatcher/` and creates `.dispatcher/.state/state.db`".
- At the time of writing, `find .` under contains only **1** `state.db` (`<claude-org-root>/.state/state.db`, inode 621604). No other state.db under worktree (`.worktrees/`) either.
- However, the situation where **the same absolute path** appears as different contents via sandbox bind-mount is hypothesis A's territory. Effectively, it can be read as "two-file equivalent of real path and shadow path".

Rejection conditions (literal version): already rejected (confirmed FS has no other `state.db`).

In total: **literal D rejected, effective D absorbed into A**.

### 3.5 Hypothesis E: simple query timing mismatch / connection cache

> `WHERE task_id LIKE '%iter-a%'` 0 hits = "reservation hasn't inserted the row, so normal"; `ORDER BY id DESC LIMIT 8` 0 hits = anomaly

**Evaluation: partial adoption / insufficient alone**

Grounds (T1 reservation by `gen_delegate_payload.py` apply):

- `_reserve_in_db` (line 374-) **always INSERTs** new tasks with `runs.status='queued'`. It calls `apply_schema(conn)` only when the DB is absent, but then creates the row via `INSERT INTO runs ...` (around lines 386-395).
- The production DB at the time of writing has `db-mystery-iter-a-audit` with `status=queued` as 1 entry (= this audit task itself), which is normal reservation behavior. Similarly, `sandbox-probe-iter-a-b1-1` is `abandoned`, and `sandbox-probe-iter-a-b1-1-writeup` / `sandbox-probe-iter-a-incorporate` exist in history as `completed`.
- → Even at 10:38, the DB should have at least 9 historical + 1 abandoned + 2 recent review/completed = 12 entries. **0 rows under `ORDER BY id DESC LIMIT 8` is anomalous**, unexplainable by E alone.
- `WHERE task_id LIKE '%iter-a%'` 0 hits could be (a) DB truly empty or (b) no matching rows. E alone can claim (b), but contradicts the `LIMIT 8` observation, so (b) is rejected.

In total, E alone cannot explain the observation. **Only as a sub-story "under A's shadow FS, DB was empty, so E observations are also consistent"**.

### 3.6 Evaluation summary

| hypothesis | plausibility | can explain observation shape (`runs=0/projects=0/events=1/IDLE`)? | keep or reject |
|---|---|---|---|
| A: sandbox shadow FS | **high** | yes (mechanical explanation completely matches fresh DB + 1 event) | **adopted (leading)** |
| B: WAL mismatch | low | no (WAL semantics keeps existing rows) | reject (possibility remains only as A's sub) |
| C: implicit rebuild | low | yes (theoretically) — but no path exists | reject |
| D-literal: separate file confusion | low | yes (theoretically) — but no other DB on FS or path | reject |
| D-effective: same path with different views | medium | yes — functionally same as hypothesis A | absorbed into A |
| E: simple timing | low | no (contradicts `LIMIT 8` observation) | reject (only as A's sub) |

→ **Conclusion of this audit**: prime suspect is **hypothesis A (under the bind-mount / overlay composition driven by sandbox auto-allow, the appearance of `.state/state.db` temporarily shadowed, and `journal_append.py` auto-created a fresh DB against that shadow)**.

## 4. Additional observations needed

### 4.1 Information desired but not obtainable in this audit

- Existence / size / mtime of `.state/state.db-wal` / `.state/state.db-shm` at 10:38
- `cat /proc/self/mountinfo` of the Secretary process at 10:38 (verify sandbox layer)
- `stat` of `.state/state.db` at 10:38 (= inode, ctime as seen via sandbox)
- Actual on/off timing of sandbox auto-allow between 10:38–10:45 (record of sandbox release events)
- bwrap startup options when "unable to open database file" occurred at 10:00 dispatcher

These can be reproduced if **row-ified in iteration B or later** (§5). Cannot be reconstructed after the fact in this iteration.

### 4.2 Verifications the audit could safely try (done at time of writing)

- Production DB `PRAGMA journal_mode/synchronous/locking_mode` (read-only): `wal / 2 / normal`
- Production DB table row counts (read-only SELECT): `runs=13, events=67, projects=4`
- Production DB `schema_migrations`: `[v1, v2]` (M2 applied, M4 cutover also complete)
- Production DB inode = 621604; only 1 `state.db` across the entire worktree
- Current absence of `state.db-wal` / `state.db-shm` (= all connections closed)

These confirm the "current production DB's physical state"; **the past 10:38 state cannot be reconstructed**. Physical confirmation of the 10:38 observation is in principle impossible (no remnants of sandbox ephemeral view).

### 4.3 Runtime instrumentation proposal

For iteration B and later, embedding the following lets next time be decisively separated:

- Add **`is_new_db = True` branch-aware instrument log** to `_db_append` of `tools/journal_append.py`, appending to `.state/journal_append-events.log` the fact that fresh DB creation occurred (fires before writing to DB, so tail can follow).
- In `connect` of `tools/state_db/__init__.py`, emit a 1-line stderr line `os.path.realpath(db_path)` and `os.stat().st_ino` (gated by DEBUG env var).
- Have the Secretary / dispatcher pane record sandbox start / release with `tools/journal_append.sh sandbox_state from=... to=...` (needed to correlate sandbox layer state with DB observation timeline).

(This audit makes **no code changes, so above is proposal only**. Implemented in separate issues / PRs.)

## 5. Impact on iteration A and next iteration proposals

### 5.1 probe checklist 1.6 candidate (new row proposal)

> **→ Correction (2026-05-09 later)**: the initial version proposed "shadow FS detection under sandbox auto-allow" as the 1.6 row, but since the true cause turned out to be cwd drift / separate DB creation, **the goal is reset**. The original draft retains value for understanding sandbox semantics but with lower priority (kept as downstream task in §5.3 proposal D). Below is the corrected 1.6 row proposal:

In `probes/checklist.md` section 1 (B1-1) or as a new category (`fs-state-db` / `fs-cwd-drift`), add the following row:

- **1.6 — detection of `.state/state.db` accidental creation / mis-reference under cwd drift**
  - Attempt (a): from an unintended cwd (e.g. `<repo-root>/.worktrees/<some-worktree>/`), execute `bash tools/journal_append.sh probe_event field=x`.
  - Attempt (b): from the same cwd, execute `python -c "import sqlite3; print(sqlite3.connect('.state/state.db').execute('SELECT count(*) FROM runs').fetchone())"`.
  - Observation (c1): before / after the attempt, capture `inode` / `mtime` / `size` / `runs count` of `.state/state.db` at **both locations**.
    - canonical: `<repo-root>/.state/state.db`
    - drift candidate: `<cwd>/.state/state.db` (= under cwd at attempt time)
  - Observation (c2): see whether the result of `find <repo-root> -name "state.db" -type f` changes before / after the attempt.
  - Expected determinations:
    - **Drift accidental creation present**: a new `state.db` is created under cwd / returns empty shape like `runs=0`.
    - **Drift accidental creation absent**: only canonical 1 file; no new DB created under cwd (= when the fix proposal §7.2 has taken effect).

- **1.6b — original 1.6 proposal (sandbox shadow FS detection, low priority)**: kept downstream as §5.3 proposal D

(Whether to add a new "fs-state-db" category related to "fs-cwd" in `probes/categories.md` legend, or to extend the existing section 1 B1-1, is decided at the Phase 1 schema design time.)

### 5.2 Proposed observation row to add to `iteration-a-results.md` §6

Add **#4** to [`iteration-a-results.md`](./iteration-a-results.md) §6 unexpected list:

> **6.4 Unexpected #4: suspicion that `.state/state.db` write became shadow-FS during sandbox auto-allow (db-mystery)**
>
> - Event: during the probe, Secretary observed runs=0, IDLE, events=1 on a SELECT immediately after issuing `journal_append.sh pr_opened`. Recovered to runs=12 at 10:45.
> - Impact: no impact on probe results themselves (Secretary restored via separate SQL UPDATE / INSERT → after `gh pr merge`, DB healthy state was visible). However, it should be recorded as **a significant observation as a probe side effect of Iteration A**, and reproducible experiment via row 1.6 is needed before Phase 1 schema design.
> - Details: see [`db-mystery-2026-05-09.md`](./db-mystery-2026-05-09.md).

(This doc only proposes the addition; does not write to `iteration-a-results.md` itself — this is audit mode. Phase 1 worker reflects it.)

### 5.3 Additions to next-iteration-proposals.md

> **→ Correction (2026-05-09 later)**: since the true cause is cwd drift, reset the main goal of proposal D. The old draft (sandbox shadow FS isolation) remains as "auxiliary observation".

The 3 existing proposals (A/B/C) in [`next-iteration-proposals.md`](./next-iteration-proposals.md) do not directly address this db-mystery. Either extend proposal A (B1-1), or separately:

- **Proposal D — db-mystery true cause verification (detection of cwd drift × separate DB accidental creation)**
  - Goal: produce material to decide which of the recurrence prevention proposals (a)–(c) in §7 to adopt. **Real-machine reproduction of hypothesis D (cwd-relative state.db resolution), and effect measurement of each fix candidate**.
  - Steps:
    1. Run §5.1 row 1.6 in both an arbitrary worktree (e.g. this audit worktree) and the canonical repo root.
    2. Verify that only 1 canonical file remains via `find <repo-root> -name "state.db" -type f` (the diff is visible if accidental creation occurs).
    3. Re-run on a branch that prototypes fix proposal (a) and confirm no accidental creation.
    4. (Auxiliary) Toggle sandbox auto-allow on/off simultaneously to observe the shadow FS hypothesis (old 1.6 = 1.6b) at the same time.
  - Time required: 30–60 min / 1 commit.
  - Recommendation: ★★★ (top priority for fixing this audit's true cause and recurrence prevention. Not directly tied to Phase 1 schema, but related to state-db reliability).

## 6. Appendix: side observation — bwrap fails on touching `~/.aws/.env`

(Information shared from Secretary during this audit. Independent of the main db-mystery story, but recorded as sandbox semantics understanding.)

- Event: each time this audit worker started Bash tool via sandbox, bwrap failed with `Can't create file at <home>/.aws/.env: No such file or directory`.
- Cause (estimate): the claude-code parent layer's permissions deny list contains `~/.aws/*`, and bwrap tries to prepare it as a bind-mount dummy file, but mkdir / touch fails because `~/.aws/.env` (the entity) does not exist.
- Impact: Bash cannot start inside the sandbox; this audit ran with `dangerouslyDisableSandbox=true` to avoid. Similar events frequently occur on the Secretary side too — known quirks in this repo environment.
- Implication: bwrap bind setup is in a **partially broken state in this repo environment, yet sandbox startup is still attempted**. When the bind dummy file cannot be prepared, whether bwrap fail-fasts or fail-softs passes that path through is unconfirmed in this audit — adds grounds for suspicion when considering A about whether the bind state of inside-sandbox `.state/` is as expected.
- Recommended follow-up: make `/proc/self/mountinfo` observation mandatory in proposal D's row 1.6. Take a 1-sample of correlation between `~/.aws/.env` existence and sandbox start success / failure.

## 7. True cause and recurrence prevention proposals (added by correction, 2026-05-09 later)

### 7.1 True cause identification

Right after PR #385 push, when the Secretary side reproduced the same `runs=0` (around 11:18 on 2026-05-09), the cause was fixed as follows:

- The Secretary's bash cwd had **drifted** into this audit worktree (`<claude-org-root>/.worktrees/db-mystery-iter-a-audit/`).
- Executing `python -c "import sqlite3; sqlite3.connect('.state/state.db')..."` etc. from that cwd, Python's sqlite3 resolves `.state/state.db` **relative to cwd** and opens `<worktree>/.state/state.db`.
- At audit start, this worktree had **no** `.state/state.db`, so `sqlite3.connect()` **auto-creates a new file** (sqlite3 spec creates an empty DB when path does not exist).
- When `tools/journal_append.sh` was started from the same cwd, `SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)` got a cwd-relative path, resolving to **`tools/journal_append.sh` inside the worktree** → REPO_ROOT is `<worktree>/` → `journal_append.py`'s `Path(__file__).resolve().parent.parent` is also `<worktree>/` → consequently writing to `<worktree>/.state/state.db` + applying schema.
- The canonical `<claude-org-root>/.state/state.db` (inode 621604) was **always at runs=13 and healthy**.

Real-machine evidence (state the audit re-observed for correction):

```text
canonical:  <claude-org-root>/.state/state.db
            inode=621604  size=167936  mtime=2026-05-09 11:21
            (runs=13, events=68, projects=4, session=SUSPENDED — healthy)

worktree:   <claude-org-root>/.worktrees/db-mystery-iter-a-audit/.state/state.db
            inode=615758  size=151552  mtime=2026-05-09 11:18
            (runs=0, projects=0, events=1..., session=IDLE — accidentally created empty DB)
```

State `find <claude-org-root> -maxdepth 5 -name 'state.db' -type f` shows 2 files. The initial version of this audit excluded the current worktree (the worktree the audit itself is in) from the search target of `find . -name state.db`, missing the existence of the accidentally created DB, and read the observation shape (`runs=0/IDLE/events=1`) as a **mechanical match with fresh DB auto-create**, then mistakenly inferred "fresh DB was newly created in sandbox shadow FS".

### 7.2 Reason for rejecting hypothesis A (fixed)

- The essence of hypothesis A is "sandbox deviated writes to `.state/` into the shadow", with **sandbox layer as a causal condition**.
- In the corrected real-machine verification, `runs=0` reproduces even with **a normal-cwd Python one-liner not going through sandbox**. Therefore sandbox is not a necessary condition = A is not the true cause of this event.
- A is **a hypothesis that has never been observed**. The "leading" rating in the initial version is based only on the indirect evidence of "match with observation shape", with no opportunity for real-machine reproduction experiment (we could not prepare an environment where sandbox can be pinned). **The decision procedure itself in the initial version is a lesson** (recorded in §7.4).

### 7.3 Recurrence prevention proposals (not implemented in this PR, follow-up proposal)

A structural problem is that state_db-related tools can resolve `.state/state.db` relative to cwd. Three fix candidates:

**Option (a) — normalize the path argument to repo-root basis in `connect()` of `tools/state_db/__init__.py`**

- When the input path is relative, anchor on git repo root (= `git rev-parse --show-toplevel` or bookmark file) and absolute-ize.
- For calls from worktrees, use git's linked worktree detection and explicitly state in the contract whether to lean on canonical repo root or worktree root (M5 agenda).
- Implementation size: medium. Impact on existing callers is broad, so the default behavior and opt-in flag need organization.

**Option (b) — correct the findings of §2.4 of this audit (re-examine path resolution of related tools)**

- §2.4 of the initial version of this audit said "`tools/journal_append.sh` / `tools/journal_append.py` are cwd-independent", but this is **only correct "inside the same worker's worktree"**.
- In environments with multiple worktrees, scripts decide REPO_ROOT based on **the path from which they were invoked**, so they are effectively cwd-relative.
- Corrected understanding: "`__file__`-based does not directly read cwd, but can become substantively cwd-dependent via the scripts' location (= worktree)".
- Immediate action: full-grep tool group call sites and add an operational guide that **explicitly specifies the canonical repo root** when starting `bash tools/...` / `python tools/...` (e.g. `bash /full/path/to/canonical/tools/journal_append.sh ...`). Current SKILL.md notation `python -m tools.state_db.importer ...` retains cwd-dependency, so an explicit note is needed.

**Option (c) — contractualize worktree-aware path resolution at state-db cutover M5**

- M2/M4 cutover concentrated SoT in `.state/state.db`, but **there is no contract on "which worktree's `.state/state.db`"**.
- In M5, fix "state.db is **only 1 file under the canonical repo root**; writes from worktrees point at canonical" as the contract.
- Option (a) is a prerequisite; operational dissemination (b) complements it.
- Add to migration-strategy.md / docs/contracts/ (outside this audit's scope).

### 7.4 Retrospective on the audit process itself (lesson for Iteration A)

The initial version of this audit **rated the hypothesis plausibility highly with static code reading alone, without stepping into real-machine refutation experiment**. As a result, the point of excluding this worktree itself from the `find . -name state.db` search target (concluded "the real thing is not there because this is the working worktree") was missed, and the wrong true cause was adopted.

Lessons:

- Even in audit-only mode, when "hypothesis evaluation depends on **natural fresh-DB generation**, enumerate at least one other path for going to a real machine to create fresh-DB" (cwd drift / worktree duplication / mount on a separate cluster, etc.).
- Using "`find . -name state.db` returned 1" as the basis for rejecting hypothesis D is fragile. We need a discipline of always checking **whether the `find` root was truly the whole repo** (in this case, `find . -name state.db` was done inside worktree A and likely listed just `./.state/state.db` as 1).
- An audit completes in **two stages: static investigation and real-machine verification**. Committing at the stage of "code reading done but reproduction experiment unperformed" as this document does is valid as an interim deliverable, but we want to establish an operational rule of "at that point, write **unverified hypothesis plausibility as Pending**" (org-retro proposal item).

---

## 8. Related materials

- [`probes/checklist.md`](../probes/checklist.md) (target for proposing 1.6, this doc §5.1)
- [`iteration-a-results.md`](./iteration-a-results.md) (parent of this doc, target for adding §6.4 proposal)
- [`next-iteration-proposals.md`](./next-iteration-proposals.md) (target for adding proposal D, this doc §5.3)
- [`tools/state_db/__init__.py`](../../../tools/state_db/__init__.py) (WAL config + ensure_m2_schema)
- [`tools/state_db/writer.py`](../../../tools/state_db/writer.py) (StateWriter / post-commit hook)
- [`tools/state_db/importer.py`](../../../tools/state_db/importer.py) (DROP TABLE path)
- [`tools/state_db/snapshotter.py`](../../../tools/state_db/snapshotter.py) (DB → markdown one-way dump)
- [`tools/journal_append.py`](../../../tools/journal_append.py) (the prime suspect for fresh DB auto-create)
- [`dashboard/org_state_converter.py`](../../../dashboard/org_state_converter.py) (DB → JSON one-way dump, post M4 cutover)
- Issue #376 (sandbox-probe iteration A spike)
- Issue #267 (M4 DB cutover)
- Issue #284 (worker archive on completed)
