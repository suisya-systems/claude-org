# Contributing to claude-org

claude-org is a self-organizing multi-agent framework built on top of Claude Code. It coordinates four roles — Lead, Dispatcher, Curator, and Worker — across panes in renga, and provides an operating template for individual operators and small teams.

Because this repository is primarily a **template for personal operation**, we welcome the following contributions over net-new features:

- Bug reports with reproduction steps
- Documentation improvements (especially on onboarding pain points in other environments)
- Generalization of role configs, hooks, and skills (abstracting personalized operating patterns)
- Safety findings (permission / hook gaps, sandbox-bypass paths, etc.)

## Setup prerequisites

Before starting development, satisfy the "Prerequisites" and "Installation" sections of [README.md](README.md). At minimum you need:

- Claude Code
- renga 0.18.0 or later
- Python 3.8+
- Git / GitHub CLI

After the initial clone, start the Lead pane with `renga --layout ops`, then **run `/org-setup` once inside Claude Code** to generate per-role `settings.local.json` files (without it you will hit a flood of permission prompts during development). See [docs/getting-started.md](docs/getting-started.md#installation) for details.

## Bug reports

File a GitHub Issue. Include the following when possible:

- Reproduction steps (minimal case)
- Expected vs. observed behavior
- OS / Claude Code version / renga version
- Diff of any relevant hook or role config changes

## How to submit a Pull Request

1. Fork this repository.
2. Branch from `main` (e.g., `feat/xxx`, `fix/yyy`, `docs/zzz`).
3. Split commits at sensible boundaries (one theme per commit).
4. Open the PR and confirm CI is green.
5. Address review feedback.

### Commit message convention

We use a Conventional Commits–style format with a prefix. Match the style of recent `git log --oneline -20` entries.

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation-only change
- `refactor:` refactor without behavior change
- `chore:` build / deps / housekeeping
- `test:` test addition or fix
- `ci:` CI config change

Examples:

```
feat(hooks): add PreToolUse guardrails for verify-bypass flags
fix(org-state): handle missing workers/ directory gracefully
docs(readme): correct renga baseline version
```

## Verification requirements

Before submitting a PR, confirm the following are green:

```bash
# Role-config integrity check (settings.json / permissions / hooks)
python tools/check_role_configs.py --include-local

# Python tests
python -m pytest tests/
```

When adding a new hook, add the corresponding test as well.

## Out of scope

The following are not handled via PR; please open an Issue first:

- Personalized operating patterns (e.g., skills targeting a specific use case)
- Optimizations for a particular environment (changes that strongly assume a path or shell)
- Large re-architectures that break the existing role structure

When in doubt, please discuss in an Issue before opening a PR.
