# Live Log Streaming for E2E Test

**Date:** 2026-04-02  
**Goal:** Surface real-time feedback during the 30-minute GPU instance startup, so users can see exactly where the process is waiting instead of staring at a blank screen.

## Problem

When running the e2e test, the orchestrator waits silently for up to 30 minutes while Vast.ai pulls the Docker image and the worker loads the model. The user has no visibility into:
- Whether something is actually happening or if it's stuck
- Which stage is slow (pulling image vs. model loading vs. waiting for health check)

Result: User stops the test after 26 minutes with zero diagnostic information.

## Solution

Make `_wait_for_worker()` stream all Docker logs live to stdout during the e2e test, with status updates and periodic heartbeats so the user always knows the process is alive.

### Key Changes

1. **Reduce log poll interval** — decrease `LOG_POLL_INTERVAL` from 30s to 5s so logs appear within ~5 seconds of being written to the instance

2. **Live streaming** — print each new log line immediately as we discover it (keep `seen_log_lines` dedup set to avoid repeats)

3. **Status transitions with timestamps** — when instance status changes (e.g. `loading` → `running`), print it with elapsed time so you know when state transitions occur

4. **Heartbeat on log silence** — if 30s pass with no new logs, print a heartbeat like `[5m45s] Still waiting, instance status: running` to confirm the process hasn't frozen

5. **Debug flag on `_wait_for_worker()`** — add optional `verbose=False` parameter so e2e test can enable it, but production library stays quiet by default

### Scope

- **E2E test only** (`test_e2e.py`) — pass `verbose=True` to enable live streaming
- Library API stays unchanged and quiet by default
- Users can manually enable verbose mode if debugging their own scripts

## Implementation

Modify `flux_worker/orchestrator.py`:
- Update `LOG_POLL_INTERVAL = 5` (was 30)
- Add `verbose=False` parameter to `_wait_for_worker()`
- Print status changes immediately with elapsed time
- Print each new log line as discovered (with verbose flag)
- Add 30s silence check to print heartbeat

Update `test_e2e.py`:
- Pass verbose flag to enable live logging during test
