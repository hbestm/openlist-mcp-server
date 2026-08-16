# Live OpenList Testing

This project has two test layers:

- Unit tests in `tests/` use fake clients and do not call a real OpenList server.
- Live smoke scripts in `scripts/` call a real OpenList server using environment variables.

## Required environment

Set these variables before running a live script:

```bash
export OPENLIST_URL="https://your-openlist.example.com"
export OPENLIST_USERNAME="your_username"
export OPENLIST_PASSWORD="your_password"
export OPENLIST_TEST_DIR="/mcp-dev-test"
```

For Windows PowerShell:

```powershell
$env:OPENLIST_URL = "https://your-openlist.example.com"
$env:OPENLIST_USERNAME = "your_username"
$env:OPENLIST_PASSWORD = "your_password"
$env:OPENLIST_TEST_DIR = "/mcp-dev-test"
```

Use a dedicated test directory when possible. Avoid running live write tests against `/`
or against user data directories.

## Scripts

Run a basic directory listing:

```bash
PYTHONPATH=src python scripts/explore_openlist.py
```

Run a live integration smoke test:

```bash
PYTHONPATH=src python scripts/live_integration.py
```

Check whether the typed task list endpoint is available on the target server:

```bash
PYTHONPATH=src python scripts/check_task_api.py
```

## What the integration script does

`scripts/live_integration.py` verifies:

- login succeeds without printing the token
- file listing works for `OPENLIST_TEST_DIR`
- a temporary folder can be created and fetched
- public settings are readable
- share listing is reachable
- typed offline download task listing is reachable

The script creates a folder named `mcp-test-<timestamp>` under `OPENLIST_TEST_DIR`
and attempts to delete it during cleanup.

## Manual live checks for the v0.4.0 fixes

When testing against a real OpenList instance, verify these behaviors that the
unit tests can only approximate:

1. **Share enable/disable/delete** — create a share, then run
   `enable_share` / `disable_share` / `delete_share` with the returned id.
   These must not return "sharing not found" (they send `?id=` as a query
   parameter now).
2. **Share list/get** — `list_shares` then `get_share_info(share_id)`.
3. **`move` task type** — after a `move` operation, `list_tasks(task_type="move")`
   must succeed (previously rejected as unsupported).
4. **Multipart upload** (requires OpenList master after v4.2.5 with the
   `multipart_enabled` admin setting): `upload_file_multipart` on a small
   file; on failure, verify `multipart_upload_status` returns a session and
   `multipart_abort_upload` discards it.
5. **Manual scan** (admin account): `start_manual_scan` on a storage mount,
   `get_manual_scan_progress`, then `stop_manual_scan`.

Note: multipart endpoints return "multipart upload is disabled" (403) if the
server build or admin setting does not support them — that is expected on
older v4.2.x deployments.

## Safety controls

The MCP server supports these environment-level safety controls:

- `OPENLIST_READONLY=true` blocks write and high-impact tools.
- `OPENLIST_ALLOWED_PATHS=/mcp-dev-test,/public` restricts OpenList path operations.
- `OPENLIST_LOCAL_UPLOAD_ROOTS=/safe/local/path` restricts local files that can be uploaded.

Do not use production admin credentials for routine live testing. Use a test account
with the minimum OpenList permissions required for the scenario.
