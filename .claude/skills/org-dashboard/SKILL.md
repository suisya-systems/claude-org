---
name: org-dashboard
description: >
  Refresh the org dashboard and open it in a browser.
  Triggers: "show me the dashboard", "visualize the situation",
  "show me the project list", "show me the big picture", etc.
effort: low
allowed-tools:
  - Bash(cat .state/dashboard.pid)
  - Bash(kill -0 *)
  - Bash(python3 dashboard/server.py *)
  - Bash(py -3 dashboard/server.py *)
  - Bash(open http://localhost:8099)
  - Bash(start http://localhost:8099)
---

# org-dashboard: open the dashboard

Start the live dashboard server (`dashboard/server.py`) and open it in a browser.
If the server is already running, just open the browser. No data generation step is needed — the server streams real-time data on its own.

## Step 1: Check server status

```bash
cat .state/dashboard.pid 2>/dev/null && kill -0 $(cat .state/dashboard.pid) 2>/dev/null && echo "running" || echo "stopped"
```

- `running` → go to Step 2.
- `stopped` → go to Step 1.5.

## Step 1.5: Start the server (only when stopped)

```bash
python3 dashboard/server.py &   # Mac/Linux
py -3 dashboard/server.py &     # Windows
```

After startup, the dashboard is reachable at `http://localhost:8099`.

## Step 2: Open it in the browser

```bash
open http://localhost:8099    # Mac
start http://localhost:8099   # Windows
```

Tell the user: "Opened the dashboard → http://localhost:8099".

## Notes

- The dashboard reflects state in real time (it auto-detects changes under `.state/`).
- No need to regenerate `data.json` manually; the server serves equivalent data via `/api/state`.
- The server is auto-started by org-start and auto-stopped by org-suspend.
