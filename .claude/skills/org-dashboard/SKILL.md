---
name: org-dashboard
description: >
  Update the organization dashboard and open it in a browser.
  Triggered by phrases like "show me the dashboard", "visualize the status",
  "I want to see the project list", or "show me the big picture".
---

# org-dashboard: Open the dashboard

Start the live dashboard server (`dashboard/server.py`) and open it in a browser.
If the server is already running, just opening the browser is enough. No data generation is needed (the server streams in real time automatically).

## Step 1: Check server status

```bash
cat .state/dashboard.pid 2>/dev/null && kill -0 $(cat .state/dashboard.pid) 2>/dev/null && echo "running" || echo "stopped"
```

- `running` → go to Step 2
- `stopped` → go to Step 1.5

## Step 1.5: Start the server (only if stopped)

```bash
python3 dashboard/server.py &   # Mac/Linux
py -3 dashboard/server.py &     # Windows
```

Once started, it becomes accessible at `http://localhost:8099`.

## Step 2: Open in browser

```bash
open http://localhost:8099    # Mac
start http://localhost:8099   # Windows
```

Tell the user: "Opened the dashboard → http://localhost:8099".

## Notes

- The dashboard reflects state in real time (it auto-detects changes to `.state/` files).
- Manual generation of `data.json` is unnecessary. The server serves equivalent data via `/api/state`.
- The server is started automatically by org-start and stopped automatically by org-suspend.
