# Guardrails Phase 2b: Design for the 3-in-1 Refactor

> Related Issue: [#80](https://github.com/suisya-systems/claude-org/issues/80)
> Status: **design only** (this PR does not include implementation; implementation will be split out into a separate Issue)
> Prerequisite: #70 Phase 1 / #79 Phase 2a have been merged
> Target files: `.hooks/lib/segment-split.sh`, `.hooks/block-*.sh`, `.claude/settings.json`

This PR documents the design and decisions for a **single-PR refactor** that bundles the three items required by Issue #80: ((1) command-allowlist integration / (3) loose-match tokenizer migration / (4) reassignment timeline tracking). It includes pseudocode, data structures, test case enumeration, phased breakdown, and open questions at a level of detail that allows the implementation Worker to write code directly from this document.

---

## 0. Why bundle these 3 items? (bundling rationale)

All three items modify **the same area of `segment-split.sh`**. If they are split into separate PRs:

- (3) changes `flatten_substitutions` at L104 from `gsub(/[\047\042]/, " ", out)` to apply only to the "append portion." This breaks cases like `eval "git commit --no-verify"` that were being detected in Phase 1 **incidentally as a side effect**.
- (4) rewrites the single-value fixed logic in `collect_assignments` + `expand_known_vars` to a snapshot-based approach. Reassignment cases like `flag=A; flag=ok; git commit "$flag"` currently remain as FPs.
- (1) adds a new API `allowlist_check()` to `segment-split.sh`, which is then called by the `block-*.sh` scripts.

If (3) is merged by itself, then only `unwrap_eval_and_bashc` from Phase 2a remains as the line of defense on the eval path, so instead of writing 3 separate sets of regression tests, it is cheaper to **bundle them into 1 PR and share pytest fixtures**. Also, because (1) reuses the tokenizer API, even if (3) is merged first, (1) would still need to touch `segment-split` again.

**Conclusion: bundling is justified as an engineering trade-off**. The downside is a larger PR, but if the commits are split into 3 stages (see §5 below) and each stage keeps pytest passing, then review and revert can still be done stage by stage.

---

## 1. Implementation language decision (continue with awk vs migrate to python)

### 1.1 Comparison table

| Item | awk | python (`py -3` + `shlex` + `re`) |
|---|---|---|
| Estimated LOC | ~150 (existing ~120 + extension ~30) | ~120 (new) |
| Heredoc preprocessing | Can be handled line-by-line in existing awk (`<<EOF` / `<<-EOF` / `<<'EOF'` / `<<\EOF` handled manually) | DIY required (same 4 forms handled with `re.compile`; line state machine is equivalent) |
| Use of `shlex` | Not possible | Possible (quoted token / nested escape / POSIX mode) |
| Use of `re` | Limited `gsub` / `match` (no lookaround, no PCRE) | Full `re` (lookbehind, named group, VERBOSE) |
| Compatibility with existing tests | Preserved (calling API unchanged) | Migration cost exists (`tests/test-block-pretooluse-hooks.sh` must be rewritten to call a new CLI) |
| Startup cost | Light (1 awk process) | python startup ~50–80 ms × 1 hook run (about 5 hooks inside 1 PreToolUse) |
| Debuggability | Low (awk is mainly printf-debug, no stack) | High (`pdb`, traceback, function-level unit tests) |
| Learning curve | Already known within the team, but implementers are limited | Consistent with the team's `tools/` scripts (`generate_worker_settings.py`, etc.) |
| Windows portability | OK with bundled Git Bash awk | Assumes `py -3` launcher (even in this worktree, `py -3` is unstable; `python` is more reliable) |
| Structured handling like single-value fixed / branch union | Weak dict/list support; must emulate with awk associative arrays | Straightforward with `dict[str, set[str]]` |

### 1.2 Recommendation: **continue with awk**

**Decision**: Python migration was considered initially, but continuing with awk is recommended for the following 3 reasons.

1. **Startup cost**: The PreToolUse hook runs **`block-no-verify.sh` / `block-git-push.sh` / `block-dangerous-git.sh` / `block-org-structure.sh` / `block-workers-delete.sh` / `block-dispatcher-out-of-scope.sh`** serially on every tool call. Each one sources `segment-split.sh`. If rewritten in python, it would become `python tools/segment_split.py < cmd.txt` called 6 times, adding a constant overhead of roughly `50–80ms × 6 ≈ 300–500ms`. That would noticeably degrade Bash tool responsiveness. With awk, it stays at a few ms.
2. **Windows portability**: Even in this worktree, `py -3` was confirmed to fail when launched through the launcher (`py -3 --version` produced a mojibake error). Calling `python` directly depends on PATH and is not portable. Bundled Git Bash `awk` is reliable.
3. **Compatibility with existing tests**: `tests/test-block-pretooluse-hooks.sh` and `tests/test-unwrap-eval-bashc.sh` already exist as shell integration tests. If awk is retained, the API stays unchanged and only new tests are added. A python migration would require creating a CLI and fully rewriting how existing shell tests invoke it, which creates the risk of "temporarily removing a safety mechanism next to a design PR."

**However, `allowlist_check()` alone remains open for discussion**: if it needs a tokenizer as robust as shlex, a hybrid design is possible where only that function is split into `tools/allowlist_check.py` and called from `segment-split.sh` via `python tools/allowlist_check.py`. This is left as an open question for Lead confirmation in §8.

### 1.3 Rejected option: full python migration
- It has advantages (`shlex` / structured data), but the short-term ROI is not there because of startup cost and test-rewrite cost.
- It should be reevaluated only after a higher-level decision is made to migrate the entire sandbox to python in the future.

---

## 2. Design for (3) Tokenizer migration

### 2.1 Responsibilities (additions relative to the current version)

| # | Responsibility | FP/TP | Implementation location |
|---|---|---|---|
| T1 | Strip comments after `#` | FP (`--no-verify` strings inside comments) | Add new `strip_comments` function before `split_segments` |
| T2 | Exclude heredoc ranges from segmentization | FP (flag-like strings hidden in heredoc bodies) | Add heredoc state to awk inside `split_segments` |
| T3 | Exclude flag detection for tokens inside quotes | FP (`git commit -m "use --no-verify carefully"`) | On the detection side (`block-no-verify.sh`), keep a **separate normalized string where quoted content is replaced with spaces** before grep |
| T4 | Explicitly re-parse `eval` / `bash -c` arguments | TP (quoted bypass) | Continue using existing `unwrap_eval_and_bashc()` (already done in Phase 2a) |
| T5 | Fix the L104 `gsub` bug in `flatten_substitutions` | Both TP/FP | Limit `gsub` not to all of `out`, but only to the **appended portion** |

### 2.2 API sketch

```bash
# Functions to be added/modified in segment-split.sh

# New: strip comments. Do not strip `#` inside quotes.
# Input: one line of Bash command text
# Output: string with everything after unquoted `#` removed
strip_comments() {
  awk '
    {
      in_dq=0; in_sq=0; out=""
      n=length($0); i=1
      while(i<=n) {
        c=substr($0,i,1)
        if(in_sq){ if(c=="\x27") in_sq=0; out=out c; i++; continue }
        if(in_dq){ if(c=="\"")  in_dq=0; out=out c; i++; continue }
        if(c=="\x27"){ in_sq=1; out=out c; i++; continue }
        if(c=="\""){   in_dq=1; out=out c; i++; continue }
        if(c=="#"){ break }      # Comment starts here (only outside quotes)
        out=out c; i++
      }
      print out
    }
  '
}

# Modified: exclude heredoc ranges from segmentization.
# Example input:
#   cat <<EOF
#   git commit --no-verify
#   EOF
#   git status
# Expected output (per segment):
#   cat <<EOF\n[HEREDOC:EOF]\n            ← one heredoc item (passed through with a tag)
#   git status
split_segments() {
  awk '
    BEGIN { in_dq=0; in_sq=0; in_bt=0; paren_depth=0; seg=""; in_heredoc=0; heredoc_tag=""; heredoc_quoted=0 }
    {
      line=$0
      # If inside a heredoc: only check for the closing tag
      if(in_heredoc){
        if(line == heredoc_tag || (heredoc_indented && line ~ "^[ \t]*" heredoc_tag "$")){
          in_heredoc=0; heredoc_tag=""
        }
        # Do not append heredoc body to seg; exclude it from inspection
        # (an alternative is to keep only a transparent marker like "[HEREDOC]")
        next
      }
      # Detect heredoc start: <<TAG / <<-TAG / <<"TAG" / <<\TAG
      # (implementation uses match() to capture it, then sets
      # in_heredoc=1, heredoc_tag=TAG, heredoc_indented=(1 if <<-))
      ... (existing segmentization logic) ...
    }
  '
}

# Modified: limit gsub only to the appended portion.
flatten_substitutions() {
  awk '
    {
      original = $0
      appended = ""
      s = $0
      while (match(s, /\$\([^()]*\)/)) {
        body = substr(s, RSTART+2, RLENGTH-3)
        appended = appended " " body
        s = substr(s, RSTART+RLENGTH)
      }
      s = $0
      while (match(s, /`[^`]*`/)) {
        body = substr(s, RSTART+1, RLENGTH-2)
        appended = appended " " body
        s = substr(s, RSTART+RLENGTH)
      }
      # Replace quote characters with spaces only in the appended portion
      # (FIX: do not destroy the original)
      gsub(/[\047\042]/, " ", appended)
      print original appended
    }
  '
}
```

### 2.3 Data flow

```
raw command (stdin)
   │
   ▼
strip_comments              ← T1 new
   │
   ▼
split_segments              ← T2 add heredoc support
   │ (segments per line)
   ▼
unwrap_eval_and_bashc       ← T4 existing (Phase 2a)
   │ (segments + unwrapped bodies)
   ▼
collect_assignments         ← rewritten in (4)
   │ (assignment snapshots per segment index)
   ▼
expand_known_vars (per seg) ← changed in (4) to receive a snapshot
   │
   ▼
flatten_substitutions       ← T5 gsub position fix
   │
   ▼
detection regex (per hook)
```

### 2.4 Supported heredoc forms

| Form | Example | End condition | indent strip |
|---|---|---|---|
| `<<TAG` | `cat <<EOF` | `^EOF$` | × |
| `<<-TAG` | `cat <<-EOF` | `^[ \t]*EOF$` | ◯ |
| `<<'TAG'` | `cat <<'EOF'` | `^EOF$` (no variable expansion) | × |
| `<<"TAG"` | `cat <<"EOF"` | `^EOF$` | × |
| `<<\TAG` | `cat <<\EOF` | `^EOF$` | × |

**Out of scope (accepted risk)**: advanced cases where the left side of `<<` contains variable expansion or command substitution, and simultaneous multiple heredocs on one line such as `cat <<A <<B`. These should be added to the README as known limitations.

---

## 3. Design for (4) Reassignment timeline tracking

### 3.1 Current problem

Right now, `collect_assignments` extracts `VAR=` from **all segments and fixes each variable to a single value** (`val` is overwritten, so later values replace earlier ones). `expand_known_vars` then expands all segments using that fixed value. As a result:

- `flag=VERIFY_SKIP; flag=ok; git commit "$flag"` → the final `flag=ok` wins, so the third segment expands to `git commit "ok"` and **is not detected** (TP miss, though this example is benign because it does not literally use `--no-verify`)
- `flag=ok; flag=--no-verify; git commit "$flag"` → the final `--no-verify` wins, so the third segment expands to `git commit "--no-verify"` and **is detected** (TP hit, current behavior)
- `flag=--no-verify; flag=ok; git commit "$flag"` → the final `ok` wins, so it becomes `git commit "ok"` and **is missed** (TP miss). This is the FP/TP inversion case discussed in item (4) of Issue #80.

**Correct behavior**: expand each `git commit` segment using the **set of values observed up to that point** (with union across branches), and block if any value in that set contains `--no-verify`.

### 3.2 Proposal: snapshot list + branch union

```
Data structures (in pseudo-Python notation; equivalent associative arrays can be used in awk):

env_at[i: int] -> dict[var: str -> set[str]]   # snapshot immediately before segment i
branch_stack: list[dict[str -> set[str]]]      # pending branches for if/&&/|| logic

# Enumeration algorithm
env = {}                          # current accumulated environment
for i, seg in enumerate(segments):
    env_at[i] = deepcopy(env)
    if seg is an assignment (VAR=val):
        env[VAR] = {val}          # linear assignment overwrites with a single value
    elif seg starts an if branch (simple detection: `if `, `case `, `[ ... ]`):
        # Branch over-approximation: since we cannot fully execute both branches in parallel,
        # if an assignment appears inside a branch, fall back conservatively by unioning it
        # with the existing value.
        in_branch = True
    elif seg is an assignment connected by `||` / `&&`:
        env[VAR] = env.get(VAR, set()) | {val}   # union with existing value
```

**Phase 2b does not need full `if/case` branch analysis**. It is enough to use the separator information already available in `split_segments` and apply the simplified rule: **if the segment connector is `&&` or `||`, assignment uses union; if it is `;`, assignment overwrites**. Reasons:

- In practice, Bash used inside hooks rarely contains `if/case`; Worker Claude mostly emits simple compound commands.
- Over-generalization would cost more to implement than the FP reduction is worth.

### 3.3 API sketch

```bash
# Modified: collect_assignments_snapshots
# Input: all segments (output of split_segments) + separator info (`;` / `&&` / `||`)
#        separator info can be added by extending split_segments to emit separator types,
#        or by running a separate split_segments_with_seps in parallel.
# Output: one snapshot per line
#   `<seg_index>\t<VAR>=<val1>,<val2>,...`
collect_assignments_snapshots() {
  awk '
    # ... update env per segment and emit env_at[i] in tabular form ...
  '
}

# Modified: expand_known_vars_at
# Input: snapshot dict (pairs like VAR=val1,val2,...) + segment text
# Output: string where $VAR is expanded into a **regex-like disjunction**
#         in the form `(val1|val2|...)`.
#         Downstream grep -E can be reused unchanged.
expand_known_vars_at() {
  local snapshot_at_i=("$@")
  # ... extend existing expand_known_vars to support multiple values ...
}
```

### 3.4 Changes on the detection side

The per-segment loop in `block-no-verify.sh` becomes:

```bash
for i in "${!SEGMENTS[@]}"; do
  segment="${SEGMENTS[$i]}"
  snapshot=( $(get_snapshot_at "$i") )
  expanded=$(printf '%s' "$segment" | expand_known_vars_at "${snapshot[@]}")
  flat=$(printf '%s' "$expanded" | flatten_substitutions)
  # grep logic below remains unchanged
done
```

### 3.5 Side effect of over-approximation

In the case `flag=--no-verify; flag=ok; git commit "$flag"`, the new logic gives `flag` the value set `{--no-verify, ok}`, so it **will block**. This means that if `flag` was assigned `--no-verify` at any earlier point, then `git commit "$flag"` is blocked. That can be seen as a false positive, but it is accepted here because **there is no legitimate reason for a Worker to attempt a dynamically constructed bypass**.

---

## 4. Design for (1) Command-allowlist integration

### 4.1 Policy

- Do not vendor the upstream `sugiyama34/cc_harness` `shell-parse.sh`. **Reason**: keeping those dependencies out of the repo is simpler than pulling in its internal library dependencies. `segment-split.sh` already has its own tokenizer, so it is more reasonable to add a thin `allowlist_check()` on top of it.
- `GOVERNED_PREFIXES` will be read from the new `.claude/settings.json` field `guardrails.governedPrefixes`.

### 4.2 Added schema in `settings.json`

```jsonc
{
  // ... existing permissions, etc. ...
  "guardrails": {
    "governedPrefixes": [
      "git push",
      "git commit",
      "gh pr create",
      "gh pr merge",
      "npm publish"
    ]
  }
}
```

### 4.3 API sketch

```bash
# Added to segment-split.sh
# allowlist_check: whether the start of a segment matches any GOVERNED_PREFIXES
# Input: segment on stdin, prefixes passed in $1 as a space-delimited array
#        (or via env var GOVERNED_PREFIXES_FILE)
# Output: if matched, exit 0 and write the matched prefix to stdout; otherwise exit 1
allowlist_check() {
  local segment
  segment=$(cat)
  segment="${segment#"${segment%%[![:space:]]*}"}"  # ltrim
  for prefix in "${GOVERNED_PREFIXES[@]}"; do
    if [[ "$segment" == "$prefix"* ]]; then
      printf '%s\n' "$prefix"
      return 0
    fi
  done
  return 1
}
```

### 4.4 Provisional governed prefixes list (open question for Lead confirmation)

In the context of `claude-org`, the following 5 items are proposed because they are judged to have **high governance value**. At the time of this document, Lead has not yet confirmed them, so they remain an open question in §8.

| # | prefix | Governance reason |
|---|---|---|
| 1 | `git push` | Publishes to a remote. Should generally go through the secretary. |
| 2 | `git commit` | Must pass the secret scanner. Combined with `block-no-verify.sh`. |
| 3 | `gh pr create` | A checkpoint where human review intervenes. A Worker creating a PR directly is a secretary-scope violation. |
| 4 | `gh pr merge` | High impact on the mainline. |
| 5 | `npm publish` | Side effects on a public registry. Not currently used directly in this repo, but useful future protection. |

**Items considered initially but dropped from the prefix list**:

- `npm install` / `pip install` / `cargo build`, etc.: side effects are local only. Sandbox rules (such as `denyWrite`) are sufficient; no need for allowlist.
- `make` / `docker`: low usage frequency in this repo; would create noise.
- `rm` / `mv`, etc.: better handled by dedicated hooks such as `block-workers-delete.sh`, which can provide more specific messages.

### 4.5 README items to add

Add the following to the guardrails section of `README.md` (in the implementation PR):

- governed prefix operating policy (who may add/remove prefixes, and through what review path)
- the provisional list and its rationale (summarize §4.4)
- hook behavior when a prefix is detected (warn + log, or immediate reject)

**Draft operating policy**: governed prefixes may only be added or removed through PR review, just like drift CI for `tools/check_role_configs.py`. Worker and secretary must not modify them at runtime.

---

## 5. Staging the integrated refactor (proposed commit split)

The implementation PR should be split into the following 3 commits. **Each commit must keep `python -m pytest tests/ tools/` and the shell integration tests green**.

### Commit 1: tokenizer migration
- `.hooks/lib/segment-split.sh`:
  - add new `strip_comments`
  - add heredoc support to `split_segments`
  - fix `gsub` position in `flatten_substitutions`
- `tests/test_segment_split.py` (new; add pytest fixtures under `tests/fixtures/`)
- Do not change how existing `block-*.sh` scripts call it (only insert `strip_comments` at the start of the pipe).
- AC: all existing TPs still pass, and FPs for comments / heredocs / quoted strings are resolved.

### Commit 2: reassignment timeline tracking
- `.hooks/lib/segment-split.sh`:
  - add new `collect_assignments_snapshots`
  - add new `expand_known_vars_at` (keep old `expand_known_vars` temporarily for compatibility, then remove it after all hooks are migrated)
- Rewrite the detection loops in the 6 scripts including `block-no-verify.sh` to use snapshots
- `tests/test_reassignment.py` (new)
- AC: all 3 cases in §3.1 behave as expected.

### Commit 3: allowlist API + settings integration + provisional governed prefixes list
- `.hooks/lib/segment-split.sh`:
  - add new `allowlist_check`
- `.claude/settings.json`:
  - add `guardrails.governedPrefixes` field (the provisional 5 items)
- New hook `.hooks/governed-prefix-warn.sh` (introduce it as **warn-only** at first to reduce rollout risk; do not reject immediately)
- Add guidance to `README.md`
- `tests/test_allowlist.py`
- AC: commands containing a prefix emit a warning log, and commands without one pass through unchanged.

### revert plan
- Each commit must be independently revertible. Commit 2 depends on the `flatten_substitutions` fix from Commit 1, so if Commit 1 is reverted alone, the PR description must clearly state that Commit 2 must also be reverted in sequence.

---

## 6. Risks & rollback conditions

### 6.1 Language-choice risk
- Because **awk was chosen**, we do not gain shlex-level robustness. This is an accepted risk and should be documented in the README: "Quoted strings and backslash escapes with nesting depth 3+ are outside the detection path. Other defense layers (sandbox / secretary review) cover this."

### 6.2 Regression test list

#### FP (currently blocked even though it should not be; this PR should fix it)

| ID | Command | Current | Expected |
|---|---|---|---|
| FP-1 | `git commit -m "do not use --no-verify"` | block | allow |
| FP-2 | `cat <<EOF`<br>`do not use --no-verify`<br>`EOF` | block | allow |
| FP-3 | `# avoid --no-verify`<br>`git commit -m ok` | block | allow |
| FP-4 | `flag=VERIFY_SKIP; flag=ok; git commit "$flag" -m x` (`VERIFY_SKIP` assumed to be a harmless constant) | block | allow (`flag={ok}` under snapshots) |
| FP-5 | `git commit -m "fix L104 gsub which used to break $(echo --no-verify) handling"` | block | keep blocking (this case is TP). **However, after the `gsub` fix, the quoted message part is preserved in `original`, while the `printf` body on the `appended` side expands to `--no-verify` and is still detected** |

#### TP (currently blocked, and should remain blocked after this PR)

| ID | Command | Expected |
|---|---|---|
| TP-1 | `git commit --no-verify -m x` | block |
| TP-2 | `git push --no-verify` | block |
| TP-3 | `eval "git commit --no-verify -m x"` | block (unwrap path) |
| TP-4 | `bash -c "git commit --no-verify"` | block |
| TP-5 | `flag=--no-verify; git commit "$flag"` | block |
| TP-6 | `flag=--no-verify; flag=ok; git commit "$flag"` | block (snapshot union) |
| TP-7 | `git commit $(printf -- '--no-verify')` | block (flatten path) |
| TP-8 | `git commit $(printf -- "--no-verify")` | block (still detected on the appended side after the `gsub` fix) |

### 6.3 Rollback conditions (kill-switch)
- If Commit 3's `governed-prefix-warn.sh` is noisier than expected, remove only that hook file from `.hooks/` (even if `guardrails.governedPrefixes` is set to an empty array in `settings.json`, the impact is still small because it is warn-only).
- If the heredoc support in Commit 1 misdetects heredoc termination, revert `split_segments` back to the Phase 1 version and keep only `strip_comments`; operations can continue with that partial rollback.

---

## 7. Acceptance Criteria mapping

Mapping between Issue #80 ACs and this document:

| AC | Corresponding section |
|---|---|
| Current FPs (comment / quotes / heredoc / reassignment) all pass | §2.1 (T1/T2/T3) + §3 + §6.2 FP-1..4 |
| No regression in existing TPs (eval-routed verify-bypass rejected) | §2.1 T4 (reuse existing unwrap path) + §6.2 TP-1..8 |
| Allowlist operational policy documented in README | §4.5 + README edits in Commit 3 |

---

## 8. Open questions (items for Lead confirmation)

1. **Do we agree with the recommendation in §1.2 to continue with awk?** The hybrid python option (only `allowlist_check` split into python) is also available.
2. **Do we agree with the provisional 5 governed prefixes in §4.4?** Are there additions or reductions to make?
3. **Behavior of the allowlist hook in §4**: should it start as warn-only, or as immediate reject? This document recommends warn-only.
4. **Acceptance of the over-approximation in §3.5**: is it acceptable to block `flag=--no-verify; flag=ok; git commit "$flag"`? This needs confirmation from a usability perspective.
5. **Is it acceptable to split the Phase 2b implementation Issue out separately from this PR** (confirming that this PR remains design only)?

---

## 9. References

- Phase 1 report: `workers/hook-phase2-feasibility/report.md` (not yet imported into this worktree; whether it was added in the PR #170 series should be checked separately)
- Related to Phase 2a: introduction of `unwrap_eval_and_bashc()` in PR #79
- Existing hooks: `.hooks/block-*.sh`, `.hooks/lib/segment-split.sh`
- Schema-driven role configs (reference: same schema-as-SOT philosophy): `tools/role_configs_schema.json`, `docs/worker-permissions-design.md`
