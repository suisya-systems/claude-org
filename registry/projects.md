# Projects Registry

A list of known projects. The Lead Claude uses it to identify which project a user request maps to.
Entries are auto-registered when a worker is dispatched. Manual additions and edits are also fine.

The "Path" column records the clone source for the project. The value drives how the worker is initialized at dispatch time:

- A URL (e.g. `https://github.com/...`) → remote repository. Fetched with `git clone {URL} {worker_dir}`.
- A local path (e.g. `C:/Users/.../existing-repo`) → existing local project. Fetched with `git clone {local_path} {worker_dir}`.
- `-` → new project (no clone source). Initialized with `git init {worker_dir}` (no clone is performed).

Note: this column is not the worker's output path (the worker operates inside `workers/{task_id}/`).
The Markdown table below is machine-parsed by `dashboard/server.py:_parse_projects` before the worker is dispatched, so do not insert additional Markdown tables (with `|---|` separators) in this section. If you need to add explanations, use plain bullet lists.

| Nickname | Project | Path | Description | Common tasks |
|---|---|---|---|---|
| Clock app | clock-app | - | A digital clock that runs in the web browser | Design changes, feature additions |
| renga | renga | https://github.com/suisya-systems/renga | Rust-based terminal multiplexer (TUI) for Claude Code | Feature additions, bug fixes, issue triage |
