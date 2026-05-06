# Watchdog

`monitor_rag.ps1` is a single-tick monitor intended to run every 15 minutes.

## Responsibilities

- Detect whether build is done.
- Detect whether build is running.
- Detect stalled embedding cache growth.
- Restart Ollama when stalled.
- Restart the build if it is down and not done.
- Avoid duplicate builds.

## Invariants

- Never start a second build when `03_build_index.py` is alive.
- Never kill `03_build_index.py` during a stall.
- Only restart Ollama during stall recovery.
- Every embedding healthcheck uses `num_ctx=8192`.
- Lock deletion is allowed only when no build worker is alive.

