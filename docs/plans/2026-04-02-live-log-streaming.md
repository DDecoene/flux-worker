# Live Log Streaming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stream all Docker logs live during e2e test with status updates and heartbeats, so users see exactly what's happening during the 30-minute GPU startup instead of staring at a blank screen.

**Architecture:** Reduce log poll interval, add verbose flag to `_wait_for_worker()`, print status changes with elapsed time, add 30s heartbeat on log silence.

**Tech Stack:** Python, requests (existing), no new dependencies.

---

## Task 1: Update log poll interval

**Files:**
- Modify: `flux_worker/orchestrator.py:16`

**Step 1: Read the current interval**

The current `LOG_POLL_INTERVAL` is set to 30 seconds. We need to reduce it to 5 seconds so logs stream more responsively.

**Step 2: Change LOG_POLL_INTERVAL**

In `flux_worker/orchestrator.py`, change line 16 from:
```python
LOG_POLL_INTERVAL = 30
```

to:
```python
LOG_POLL_INTERVAL = 5
```

**Step 3: Commit**

```bash
git add flux_worker/orchestrator.py
git commit -m "perf: reduce log poll interval from 30s to 5s for live feedback"
```

---

## Task 2: Add verbose parameter to _wait_for_worker()

**Files:**
- Modify: `flux_worker/orchestrator.py:101-152`

**Step 1: Update function signature**

Change the function signature on line 101 from:
```python
def _wait_for_worker(api_key: str, instance_id: int, token: str) -> str:
```

to:
```python
def _wait_for_worker(api_key: str, instance_id: int, token: str, verbose: bool = False) -> str:
```

**Step 2: Commit**

```bash
git add flux_worker/orchestrator.py
git commit -m "feat: add verbose parameter to _wait_for_worker()"
```

---

## Task 3: Update orchestrator.generate() to pass verbose flag

**Files:**
- Modify: `flux_worker/orchestrator.py:19-82`

**Step 1: Add verbose parameter to generate()**

Add `verbose=False` parameter to the `generate()` function signature on line 19. The signature becomes:
```python
def generate(
    prompts,
    output_dir="./output",
    vastai_api_key=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
    min_inet_down_mbps=None,
    verbose=False,
) -> GenerateResult:
```

**Step 2: Pass verbose to _wait_for_worker()**

On line 77, change:
```python
worker_url = _wait_for_worker(config.vastai_api_key, instance_id, token)
```

to:
```python
worker_url = _wait_for_worker(config.vastai_api_key, instance_id, token, verbose=verbose)
```

**Step 3: Commit**

```bash
git add flux_worker/orchestrator.py
git commit -m "feat: thread verbose flag through generate() to _wait_for_worker()"
```

---

## Task 4: Add silence tracking and heartbeat to _wait_for_worker()

**Files:**
- Modify: `flux_worker/orchestrator.py:101-152`

**Step 1: Add silence tracking variables**

At the start of `_wait_for_worker()`, after line 106 (`last_status = None`), add:
```python
    last_log_time = time.time()
    silence_threshold = 30  # print heartbeat if no logs for 30s
```

**Step 2: Update last_log_time when logs are printed**

In the log polling section (around line 142-148), after we print a log line, update the time. Change the loop from:
```python
        # Poll logs periodically
        now = time.time()
        if now - last_log_poll >= LOG_POLL_INTERVAL:
            logs = vastai.get_instance_logs(api_key, instance_id)
            for line in logs.splitlines():
                if line and line not in seen_log_lines:
                    print(f"  [gpu] {line}")
                    seen_log_lines.add(line)
            last_log_poll = now
```

to:
```python
        # Poll logs periodically
        now = time.time()
        if now - last_log_poll >= LOG_POLL_INTERVAL:
            logs = vastai.get_instance_logs(api_key, instance_id)
            has_new_logs = False
            for line in logs.splitlines():
                if line and line not in seen_log_lines:
                    if verbose:
                        print(f"  [gpu] {line}")
                    seen_log_lines.add(line)
                    has_new_logs = True
            if has_new_logs:
                last_log_time = now
            last_log_poll = now
```

**Step 3: Add heartbeat on silence**

After the log polling block, before `time.sleep(HEALTH_POLL_INTERVAL)`, add:
```python
        # Print heartbeat if no logs for 30s and we're waiting
        if verbose and (now - last_log_time) > silence_threshold:
            elapsed = int(time.time() - (deadline - HEALTH_TIMEOUT))
            print(f"  [heartbeat] {elapsed}s elapsed, instance status: {status}")
            last_log_time = now
```

**Step 4: Commit**

```bash
git add flux_worker/orchestrator.py
git commit -m "feat: add 30s heartbeat on log silence for live feedback"
```

---

## Task 5: Print status changes with elapsed time

**Files:**
- Modify: `flux_worker/orchestrator.py:115-119`

**Step 1: Update status change print**

Replace lines 116-119:
```python
        if status != last_status:
            elapsed = int(HEALTH_TIMEOUT - (deadline - time.time()))
            print(f"  Instance status: {status} ({elapsed}s elapsed)")
            last_status = status
```

with:
```python
        if status != last_status:
            elapsed = int(time.time() - (deadline - HEALTH_TIMEOUT))
            print(f"  Instance status: {status} ({elapsed}s elapsed)")
            last_status = status
```

(Note: The elapsed time calculation was already correct in the code. This just ensures it stays that way.)

**Step 2: Commit**

```bash
git add flux_worker/orchestrator.py
git commit -m "fix: correct elapsed time calculation in status updates"
```

---

## Task 6: Update test_e2e.py to enable verbose mode

**Files:**
- Modify: `test_e2e.py:12-19`

**Step 1: Add verbose=True to generate() call**

Change the `generate()` call in `test_e2e.py` from:
```python
    result = generate(
        prompts=["a red cube"],
        output_dir="./e2e_output",
        max_gpu_price=0.50,
        min_vram_gb=16,
        min_cuda_version=12.0,
        disk_gb=50,
    )
```

to:
```python
    result = generate(
        prompts=["a red cube"],
        output_dir="./e2e_output",
        max_gpu_price=0.50,
        min_vram_gb=16,
        min_cuda_version=12.0,
        disk_gb=50,
        verbose=True,
    )
```

**Step 2: Commit**

```bash
git add test_e2e.py
git commit -m "test: enable verbose logging in e2e test"
```

---

## Task 7: Manual test the e2e test

**Step 1: Run the e2e test**

```bash
python test_e2e.py
```

**Expected output:**
- Instance creation message
- Status changes with elapsed time (e.g. `Instance status: loading (5s elapsed)`)
- Docker log lines streamed live as they arrive (e.g. `[gpu] Pulling docker image...`)
- Heartbeat lines every 30s with no new logs (e.g. `[heartbeat] 65s elapsed, instance status: running`)
- Eventually `/health` check succeeds and generation starts
- Final "Instance destroyed" message

**Step 2: Verify no errors**

Ensure the test completes without exceptions and returns exit code 0 on success.

**Step 3: Commit test results**

No commit needed for this step—it's just verification.

---

## Summary of Changes

| File | Change |
|------|--------|
| `flux_worker/orchestrator.py` | Reduce `LOG_POLL_INTERVAL` to 5s, add `verbose` parameter, implement heartbeat, update status printing |
| `test_e2e.py` | Pass `verbose=True` to enable live logging |

**Default behavior (library users):** `verbose=False` by default, so production CLI stays quiet and doesn't spam logs.

**E2E test behavior:** `verbose=True`, so developers see everything happening during the wait.
