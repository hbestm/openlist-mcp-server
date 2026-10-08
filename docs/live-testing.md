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

Use a dedicated test directory. The write suites (`fulltest_*`, `live_test_*`)
require `OPENLIST_TEST_DIR` and refuse to start without it — they create and
delete a timestamped subtree there and nowhere else, so pointing them at `/` or
at user data would destroy real files. Point it inside an existing writable
mount, e.g. `/scratch/mcp` on a scratch storage.

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
4. **Multipart upload** (OpenList **v4.2.5+** with the `multipart_enabled`
   admin setting turned on): `upload_file_multipart` on a small file and on a
   multi-chunk file (>1 MiB). To verify resume, interrupt a session and re-run
   the same upload — the tool sends the payload MD5 (`X-File-Md5`) as the
   identity proof, so the server reuses the same session and skips
   already-received chunks; check the second run reports the same `upload_id`.
   `multipart_upload_status` on a live session returns the received ranges and
   `multipart_abort_upload` discards it.
5. **Manual scan** (admin account): `start_manual_scan` on a storage mount,
   `get_manual_scan_progress`, then `stop_manual_scan`.

Note: multipart endpoints return "multipart upload is disabled" (403) if the
server build or admin setting does not support them — that is expected on
older v4.2.x deployments (v4.2.4 and earlier).

## Safety controls

The MCP server supports these environment-level safety controls:

- `OPENLIST_READONLY=true` blocks write and high-impact tools.
- `OPENLIST_ALLOWED_PATHS=/mcp-dev-test,/public` restricts OpenList path operations.
- `OPENLIST_LOCAL_UPLOAD_ROOTS=/safe/local/path` restricts local files that can be uploaded.

Do not use production admin credentials for routine live testing. Use a test account
with the minimum OpenList permissions required for the scenario.

## Automated live-regression scripts (v0.4.0)

The repository ships ready-to-run live suites that drive the *real* MCP tool
functions (and, for the e2e script, the actual stdio server) against a live
OpenList. All writes are confined to a timestamped subtree under
`OPENLIST_TEST_DIR` and removed afterwards; global admin destructives (index
build/clear, `reset_api_token`, `clear_*` on other users' data,
`save_settings`) are deliberately not executed. Nothing is hard-coded to a
particular mount, so the suites run against whatever scratch directory you
point them at.

```bash
export OPENLIST_URL=http://host:5244 OPENLIST_USERNAME=admin \
       OPENLIST_PASSWORD=... OPENLIST_ALLOW_HTTP=true \
       OPENLIST_TEST_DIR=/scratch/mcp
python scripts/fulltest_capabilities.py  # 64 checks — fs, shares, tasks, admin, archives, torrents, re-login
python scripts/fulltest_mcp_tools.py     # 63 checks — every tool group, real payloads
python scripts/fulltest_stability.py     # 16 checks — repeats, concurrency, bad inputs, re-auth
python scripts/fulltest_mcp_e2e.py       # 22 checks — full MCP protocol over stdio
python scripts/live_test_multipart.py    # 10 checks — resumable multipart upload (v4.2.5+)
python scripts/live_test_p1_admin.py     # 30 checks — storage CRUD, driver configs, user write, metadata lifecycle
# safety gates (subprocess envs):
OPENLIST_READONLY=true TEST_MODE=readonly python scripts/fulltest_safety_gates.py
OPENLIST_ALLOWED_PATHS="$OPENLIST_TEST_DIR" OPENLIST_BLOCKED_PATH=/elsewhere \
    TEST_MODE=allowed_paths python scripts/fulltest_safety_gates.py
```

`fulltest_safety_gates.py` needs a second path in `allowed_paths` mode:
`OPENLIST_BLOCKED_PATH`, a location the allowlist must reject. It is only ever
aimed at, never written to — every operation against it has to fail before
reaching the server.

Both modes also cover the tools that trade in URLs and credentials, not just the
ones that take a path and write to it: a download URL, a direct-upload
capability or a generated `.torrent` for an outside path is itself the leak, and
`readonly` has to reject the ones that write.

Reference results on OpenList v4.2.6 (2bdf16d): 64/64, 63/63, 16/16, 22/22,
21/21 (gates: 12 readonly + 9 allowed-paths), 10/10 (multipart) and 30/30
(P1 admin + metadata) — all green, with 3 checks skipped.

`live_test_p1_admin.py` covers the metadata lifecycle end to end: it creates a
directory, attaches metadata, reads it back, updates it, and deletes it — then
asserts the directory itself survived, since `delete_meta` removes the record,
not the files.

Those skips are deployment-dependent rather than failures, and each one names
its reason: `fs/recursive_move` is not implemented by OpenList v4.2.x (the MCP
tool falls back to move+rename, which `fulltest_mcp_tools.py` exercises at the
tool level), a server with `multipart_enabled` accepts the multipart init that
older releases rejected, and a driver that finishes uploads inline never reports
an upload task id. Run on a v4.2.2 box or against an SFTP mount and those three
turn into real checks again.

`live_test_p1_admin.py` exercises the v0.5.0 admin-write tools with fully
reversible changes: it creates a temporary `Local` storage mounted on
`/mcp-p1-*` (root `/tmp`), exercises update/disable/enable/delete, writes an
aria2 config and restores it (the server keeps built-in setting keys, so
"restore" writes the previous values back), and creates/updates/removes a
throwaway user. It cleans up after itself; a failed probe (e.g. aria2
offline) is expected and reported as "configuration saved, but the client
probe failed".
