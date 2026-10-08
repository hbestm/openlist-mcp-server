# Changelog

All notable changes to the OpenList MCP Server are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.6.0] — 2026-10-07

### Added
- **mcp 2.x support** — the SDK renamed `FastMCP` to `MCPServer` and moved it
  from `mcp.server.fastmcp` to `mcp.server.mcpserver`. A single import shim
  (`src/openlist_mcp/_compat.py`) now resolves whichever class the installed SDK
  provides, so the server runs unchanged on mcp 1.x **and** mcp 2.x. The three
  APIs this project uses (`FastMCP(name=…, instructions=…)`, the `@mcp.tool()`
  decorator, and `mcp.run()`) keep their signatures across the rename.

### Changed
- Dependency range widened from `mcp>=1.0.0,<2.0.0` to `mcp>=1.0.0,<3.0.0`.
  The previous upper bound was a workaround for the rename, not a real
  incompatibility; it also meant fresh installs and upgrades could not pick up
  any 2.x release. Verified against both **mcp 1.29.0** and **mcp 2.3.0**:
  ruff, `ruff format --check`, mypy, all 172 unit tests, and a stdio
  `initialize` → `tools/list` handshake reporting all 107 tools.
- Merged upstream `main` (PR #4, "migrate FastMCP → MCPServer for mcp==2.0").
  Upstream's version supported 2.x only; this merge keeps its 2.x support while
  retaining 1.x compatibility.
- mypy: `mcp.server.mcpserver` and `mcp.server.fastmcp` are declared
  `ignore_missing_imports`, since exactly one of the pair is absent depending on
  the installed SDK; `openlist_mcp._compat` opts out of unused-ignore reporting
  for the same reason.

### Notes
- On mcp 2.x the client-side result models use snake_case (`server_info`,
  `is_error`) where 1.x used camelCase (`serverInfo`, `isError`). Neither the
  server nor the test suite reads those fields, so this affects only external
  automation scripted against the client SDK.


## [0.5.0] — 2026-08-16

### Added
- **Storage management (write)** (`admin.py`) — 6 new tools: `create_storage`,
  `update_storage`, `delete_storage`, `enable_storage`, `disable_storage`,
  `load_all_storages`. `update_storage` reads the current config first and only
  applies the provided fields, so unspecified settings are preserved.
  `create_storage` surfaces a readable note when the server persisted the
  record but mounting failed (e.g. bad `root_folder_path`), pointing at
  `update_storage`/`delete_storage` to fix or remove it.
- **Offline-download client configuration** (`admin.py`) — 12 new tools:
  `set_aria2`, `set_qbittorrent`, `set_transmission`, `set_115`,
  `set_115_open`, `set_123_pan`, `set_123_open`, `set_pikpak`, `set_thunder`,
  `set_thunderx`, `set_thunder_browser`, `set_guangyapan`. The server saves
  these settings before probing the client, so a failed probe (e.g. aria2
  offline) is reported as "configuration saved, but the client probe failed"
  instead of a hard error that hides the persisted change.
- **User management (write)** (`admin.py`) — 2 new tools: `create_user`
  (rejects guest/admin roles client-side as the server does) and
  `update_user` (read-then-merge; role cannot change via API).
- Admin skill group grows 22 → 42 tools; total tool count 87 → **107**.
  Tool counts in the startup banner are now derived at runtime.

### Fixed
- **`delete_setting` never deleted anything**: the server reads the key from
  the query string (`c.Query("key")`), but the tool sent it in the JSON body,
  so the key was always empty. Now sends `params={"key": key}`.

### Changed
- Update/create payloads for storage and user are built by read-then-merge so
  partially specified updates cannot zero out untouched fields.

## [0.4.1] — 2026-08-16

### Fixed
- **Multipart resume never actually resumed against a live server**: OpenList
  (post-v4.2.5) only lets a client resume an in-progress session when it can
  prove the retry is the same file — it requires a matching `X-File-Md5`
  (path+size alone is deliberately rejected). The tools never sent a hash, so
  the server terminated the stale session and re-uploaded everything. The
  uploader now always computes the payload MD5 (in-memory or streamed from
  disk) and sends it on init; verified live that a retry reuses the same
  `upload_id` and skips already-received chunks. (`transfer.py`)
- **Chunk slicing now follows the server's session chunk size** returned by
  init, instead of the locally-computed value, so slices stay aligned when the
  server clamps or resumes an older session with a different chunk size. (`transfer.py`)

### Changed
- Live regression infrastructure (confined to `/test`, auto-cleanup) added
  under `scripts/`: `fulltest_mcp_tools.py` (60 checks), `fulltest_stability.py`
  (16), `fulltest_mcp_e2e.py` (22), `fulltest_safety_gates.py` (13),
  `live_test_multipart.py` (9). Docs: `docs/live-testing.md`.
- Multipart upload verified working end-to-end against a live **OpenList
  v4.2.5** with `multipart_enabled=true` (25 MiB / 4 chunks, server-side size
  and content-MD5 match, resume reuses the session). The earlier "requires
  master after v4.2.5" note is superseded — v4.2.5 already ships the API.

## [0.4.0] — 2026-06-14

### Fixed
- **Share enable/disable/delete/cancel were broken against the real OpenList
  API**: OpenList reads the share id from the query string
  (`c.Query("id")` — verified in v4.2.2, v4.2.5, and master), but the tools
  sent it in the JSON body, so every call failed with "sharing not found".
  All four now send `params={"id": ...}`; tests for enable/disable/cancel
  previously encoded the wrong contract and now assert the query string.
  (`share.py`, `tests/test_share_tools.py`)
- **Fresh installs crashed at import**: `mcp>=1.0.0` resolved to mcp 2.x,
  which removed `mcp.server.fastmcp`. Dependency is now capped at
  `mcp>=1.0.0,<2.0.0`. (`pyproject.toml`)
- **`OPENLIST_ALLOWED_PATHS` allowlist bypass**: `tree`, `disk_usage`, and
  `find_duplicates` traversed directories without checking the allowlist.
  All three now call `enforce_path_allowed`. (`fs.py`, `advanced.py`)
- **`delete_share` unit test was red**: The test asserting the query-param
  contract was left stale by the v0.3.2 change; it now passes again.
- **`_reject_internal_url` blocked the event loop**: synchronous
  `socket.getaddrinfo` inside offline-download tools froze the MCP server
  during DNS resolution. Now uses `asyncio.get_running_loop().getaddrinfo`.
  (`advanced.py`)
- **Startup banner printed a literal `{__version__}`**: the version line was
  missing its `f` prefix. (`server.py`)
- **`torrent_upload_parse` crashed on malformed base64**: now returns a
  friendly error instead of raising `binascii.Error`. (`advanced.py`)
- **Masked driver names in `list_drivers` docstring**: restored readable
  examples (Local, S3, OneDrive, 115, 189PC, AliyunDrive, ...). (`admin.py`)

### Added
- **Resumable multipart upload support** (requires an OpenList build with the
  multipart API — master after v4.2.5 — and the `multipart_enabled` setting):
  - `upload_file_multipart` — base64 content via `/fs/multipart/*`.
  - `multipart_upload_local_file` — stream local files from disk without
    loading them into memory.
  - `multipart_upload_status` — query progress by upload_id or path+size.
  - `multipart_abort_upload` — discard an in-progress session (confirm-gated).
  - Re-invoking an upload with the same path/name/size resumes the session;
    already-received chunks are skipped via the server's `received` ranges.
  (`client.py`, `transfer.py`)
- **`get_direct_upload_info`** — client-side direct upload credentials for
  storage backends that support direct upload (S3, etc.). (`transfer.py`)
- **Manual scan administration**: `start_manual_scan`, `stop_manual_scan`,
  `get_manual_scan_progress` — one-off scans of a storage mount. (`admin.py`)
- **`move` task type** — previously missing from `TASK_TYPES`, so move tasks
  could not be listed/managed. (`task.py`)

### Changed
- Tool count increased from 79 to **87** across all categories.
- `upload_file` / `upload_local_file` now report a synchronous upload that
  returns `{"value": null}` from OpenList as "uploaded successfully" instead
  of "Upload task created". (`transfer.py`)
- Banner and README tool counts are no longer hardcoded where feasible;
  startup banner now reports dynamic counts.
- `docs/api-compatibility.md` rewritten: corrected task list verb (GET, not
  POST), documented the share query-string contract, the multipart API, the
  move task type, direct upload, and manual-scan endpoints.

## [0.3.3] — 2026-06-10

### Fixed
- **`_list_items` missing import causes NameError**: `fs.py` and `advanced.py`
  called `_list_items()` without importing it. Extracting shared walker code
  in v0.3.2 omitted the import lines — any directory-traversal tool
  (`find_duplicates`, `tree`, `disk_usage`, `mirror`) would crash at runtime
  with `NameError: name '_list_items' is not defined`. Added `from . import
  _list_items` to both files. (`fs.py`, `advanced.py`)

### Changed (Cleanup)
- **`_human_size` deduplicated**: Two identical copies existed in `advanced.py`
  and `fs.py`. Moved to shared `_list_items` module in `tools/__init__.py`,
  both files now import it. Reduces duplicate code and ensures consistent
  formatting everywhere. (`__init__.py`, `advanced.py`, `fs.py`)
- **`import httpx` moved to module top**: Was inside a function body
  (`content_preview` tool), which causes repeated import overhead on each
  call and breaks PEP 8 conventions. Moved to module-level imports.
  (`advanced.py`)


## [0.3.2] — 2026-06-10

### Security
- **`update_current_user` bypasses `OPENLIST_READONLY`**: When the server is
  configured with `OPENLIST_READONLY=true`, this tool could still change
  passwords and base paths — a privilege escalation gap. Other write tools
  (`add_ssh_key`, `delete_ssh_key`) correctly called `enforce_writable()`,
  but `update_current_user` was missed. Now blocked like all other write
  operations. (`auth.py`)
- **`generate_torrent` bypasses `OPENLIST_READONLY`**: Generating `.torrent`
  files is a write operation (creates files on the server), but it lacked
  the `enforce_writable()` check. In readonly mode, the tool would silently
  proceed, potentially filling the server with torrent metadata files despite
  the readonly setting. (`advanced.py`)

### Fixed
- **`delete_share` sends wrong parameter format**: Used `params=` (query
  string) while all other share tools (`cancel_share`, `enable_share`,
  `disable_share`) use `json=` (request body). This is inconsistent — POST
  requests with query parameters may be ignored or rejected by the OpenList
  API, making `delete_share` silently fail while reporting success. The
  root cause was a copy-paste oversight when the tool was added in v0.2.8.
  (`share.py`)
- **`mirror` may fail on nested directories**: When syncing directory trees,
  files could be copied before their parent directories exist at the
  destination. The operation relied on CPython's dict insertion order
  (3.7+ behavior) rather than explicit ordering — if the API returns files
  before directories, the copy would fail with a "parent not found" error.
  Added `to_copy.sort()` to guarantee directories are always created first.
  (`fs.py`)
- **`tree` misidentifies files as directories on some API versions**: Used
  dict equality (`i not in dirs`) to distinguish files from directories,
  which depends on the entire dict object being identical — fragile across
  OpenList API versions. Changed to explicit type field check
  (`i.get("type") not in (1, "dir", "folder")`) which is robust against
  API response changes. (`fs.py`)

### Changed
- **Extracted shared `_list_items` helper**: 4 identical recursive directory
  walkers existed in `find_duplicates`, `tree`, `disk_usage`, and `mirror` —
  each with their own copy of the API call, error handling, and item parsing
  logic. A bug fix in one would easily be missed in another. Consolidated
  into a single `_list_items()` utility in `tools/__init__.py`, reducing
  ~50 lines of duplicate boilerplate and ensuring consistent behavior across
  all directory-traversal tools.

## [0.3.1] — 2026-06-06

### Added
- **`OPENLIST_SKILLS` environment variable**: Select which tool groups to load.
  - `core` (default) — 25 tools: auth + file browsing + upload/download
  - `default` — 44 tools: core + task management + shares
  - `all` — all 79 tools
  - Custom: `OPENLIST_SKILLS=fs,transfer,task`
- **Shared `skills.py` module**: Single source of truth for group metadata
  (`SKILL_GROUP_META`, `SKILL_PRESETS`, `resolve_skills()`, `count_tools()`).
- **Tests for skills module**: 21 test cases covering presets, resolution, counting, sync.
- **CI automation**: `.github/workflows/ci.yml` — ruff/mypy/pytest/coverage on push/PR.
- **Upgrade migration notice**: Banner and startup log prompt when only core tools are loaded.
- **Invalid group name warning**: `resolve_skills()` logs a warning for unrecognized group names.
- **`OPENLIST_SKILLS` in docs**: `.env.example`, README, README-zh updated.
- Startup banner now dynamically shows loaded groups and tool counts.

### Changed
- **Default loaded tools reduced from 79 to 25** (`OPENLIST_SKILLS=core`).
  Users who need all tools set `OPENLIST_SKILLS=all`.
- Auth/public tools are always loaded (login, SSH keys, profile update).
- `SKILL_GROUP_META`: removed hardcoded `count` field, uses `len()` dynamically.
- `__init__.py`: version now read dynamically from `pyproject.toml` (no static fallback).

### Fixed
- **401 auth bypass**: `request()` in `client.py` skipped authentication on the
  first attempt due to `attempt > 1` guard added with SQLITE_BUSY retry.
  `ensure_authenticated()` is now called once before the retry loop.

### Security
- **All confirm prompts** now prefixed with `⚠️` for better AI agent visibility:
  file delete, SSH key delete, settings save/delete, index operations,
  API token reset, share cancel/delete, task cancel/delete/batch ops.


## [0.2.12] — 2026-06-04

### Added
- **SQLITE_BUSY auto-retry**: `OpenListClient.request()` now retries up to 3
  times with exponential backoff (2s, 4s) on SQLite database lock errors.
  All 79 tools benefit — no per-tool retry code needed.

### Fixed
- **Magnet links rejected** by SSRF protection: `magnet:` URLs are now allowed
  in `offline_download` and `batch_download`. SSRF check is skipped for magnet
  links (they have no hostname to resolve).
- **FTP/SFTP downloads blocked**: `ftp://` and `sftp://` URLs are now
  allowed alongside `http`/`https`/`magnet` in download tools. All
  hostname-based schemes still go through SSRF IP validation.

### Changed
- `_SAFE_SCHEMES` constant extracted at module top for single-source-of-truth
  on allowed download URL protocols: `http`, `https`, `magnet`, `ftp`, `sftp`.

## [0.2.11] — 2026-06-04

### Added
- **Admin search index management**: `build_search_index`, `update_search_index`,
  `stop_indexing`, `clear_search_index` — full lifecycle management of the search
  index (all require `confirm=true` for safety).
- **Admin settings write**: `save_settings` — update one or more global settings
  atomically; `delete_setting` — remove a custom setting (both require `confirm=true`).
- **Admin user management (read-only)**: `list_users` — list all user accounts with
  pagination; `get_user` — get detailed info for a specific user by ID.
- **Admin meta management (read-only)**: `list_metas` — list all metadata
  configurations; `get_meta` — get metadata details by ID.
- **Admin driver detail**: `list_drivers_detail` — list all storage drivers with
  full configuration templates (more detailed than `list_drivers`).
- **Admin token management**: `reset_api_token` — generate a new API token
  (requires `confirm=true`).
- 32 new tests covering all new tools (confirm gating, valid payloads, empty inputs).

### Changed
- Tool count increased from 67 to **79** across all categories.
- Startup banner updated with new admin tool listings.
- `admin.py` module evolved from read-only to hybrid read/write,
  importing `enforce_writable` and `validate_pagination`.

## [0.2.10] — 2026-06-01

### Fixed
- `list_tasks` now uses `GET` instead of `POST` for OpenList v4.2.2 compatibility
- Unit tests for `list_tasks` aligned with the new `GET` endpoint (all 72 tests passing)
- Startup banner tool count corrected from 65 to 67
- `__version__` NameError crash — added missing `from . import __version__` to `server.py`
- `mirror` pull mode now correctly copies files from dst to src (was wrongly copying src to dst, same as push)
- `_fetch_one` in `list_tasks(all)` now logs errors via `logger.warning` instead of silently swallowing them
- `delete_ssh_key` now requires `confirm=true` to prevent accidental deletion
- `add_ssh_key` now respects `OPENLIST_READONLY` via `enforce_writable`
- `update_share` uses `get_share_info` instead of pulling all 200 shares to find current files

### Changed
- HTTP connections now require explicit `OPENLIST_ALLOW_HTTP=true` — server rejects HTTP by default with a clear error message

### Infrastructure
- `import asyncio` in `task.py` and `import base64` in `advanced.py` moved from function body to module top
- Redundant `validate_path()` call removed from `get_archive_meta` (already inside `enforce_path_allowed`)

## [0.2.9] — 2026-06-01

### Added
- `get_archive_meta` — get archive metadata (format, encryption, comment, file tree) without extracting.
- `torrent_upload_parse` — parse a `.torrent` file via multipart form upload, returns info + reusable base64 data.
- `list_tasks(task_type="all")` — query all 6 task categories concurrently and merge results.

### Infrastructure
- `client.py`: add `multipart_form()` method for multipart/form-data POST requests.

## [0.2.8] — 2026-05-31

### Added
- `batch_cancel_tasks`, `batch_delete_tasks`, `batch_retry_tasks` — batch task operations.
- `clear_done_tasks`, `clear_succeeded_tasks`, `retry_failed_tasks` — one-shot task cleanup.
- `tree` — recursive directory tree with icons.
- `disk_usage` — disk usage summary by directory and file type.
- `find_duplicates` — detect duplicate files by name+size or size only.
- `content_preview` — preview text file content via range request.
- `batch_download` — download multiple URLs at once via offline download.
- `mirror` — recursive directory sync (push/pull/mirror modes, dry-run support).

### Added (Phase 3 — Read-only Admin)
- `list_storages`, `get_storage_info` — view storage backends (read-only).
- `list_drivers`, `get_driver_info` — view storage driver types.
- `get_settings`, `get_setting` — view global server settings (read-only).
- `get_index_progress` — view search index building progress.

### Added (Phase 4 — High-Frequency)
- `get_archive_extensions` — list supported archive formats.
- `get_share_info` — get details of a single share link.
- `list_my_ssh_keys`, `add_ssh_key`, `delete_ssh_key` — SSH public key management.
- `update_current_user` — update password or base path.
- `remove_empty_dirs` tool — recursively remove empty directories after cleanup operations.
- `update_share` tool — modify existing share links (password, expiration, files, etc.).
- `enable_share` / `disable_share` tools — temporarily toggle share links without deleting them.
- `parse_torrent` tool — parse `.torrent` file content (base64) and return file list/metadata.
- `generate_torrent` tool — generate a `.torrent` file for an existing file on the server.
- `torrent_rapid_upload` tool — attempt server-side rapid import from torrent data (requires CAS).

### Changed
- `create_share` now uses `files: list[str]` instead of `path: str` — OpenList v4.2.2 API requires a file list.
- `cancel_share` now calls `/share/disable` internally (the old `/share/cancel` endpoint no longer exists).
- `delete_share` now uses query parameter `?id=` instead of JSON body — matches OpenList v4.2.2 API.
- Startup guide updated from 32 to 40 tools.

### Fixed
- `search_files` parameter names corrected to match OpenList API:
  `path` → `parent`, `keyword` → `keywords`, added `scope` parameter.
  (PR #3 by @chung1912)
- Fixed 3 runtime crashes: missing `OpenListError` import, undefined `_human_size` function,
  and `request()` json parameter type annotation.
- Code quality: removed dead code, fixed ruff warnings, resolved mypy type errors.
- All source files reformatted with `ruff format`.
- `create_share` no longer returns "must add at least 1 object" error (was sending wrong payload format).
- `cancel_share` / `delete_share` no longer return 500 errors on OpenList v4.2.2.

### Security
- SSRF prevention: `offline_download` now resolves hostnames via DNS and blocks requests to
  private/internal IP ranges (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16,
  169.254.0.0/16, ::1/128, fc00::/7, fe80::/10).
- `upload_file` now enforces a 100 MB limit on base64 content to prevent memory exhaustion.
- `copy`/`move` tools now check `enforce_writable` before `enforce_path_allowed` to prevent
  information leakage in readonly mode.
- `server.py` version string is now dynamically read from `__version__` instead of hardcoded.

## [0.2.7] — 2026-05-30

### Added
- `list_download_tools` tool — query available offline download tools (aria2, Transmission,
  qBittorrent, etc.) configured on the OpenList server.
- `OPENLIST_TOTP_SECRET` environment variable — auto-generate TOTP codes during login.
  When configured, 2FA is handled automatically without manual code input. (PR #2 by @chung1912)

### Changed
- `offline_download` docstring updated to document all supported download tools.
- Startup guide updated to reflect 32 tools across all categories.

### Fixed
- `validate_path`: component-level `..` detection — no longer rejects legitimate filenames
  like `backup..2024.tar.gz`.

## [0.2.6] — 2026-05-30

### Added
- `tools/advanced.py` module with:
  - `offline_download` — download files from a remote URL directly to the OpenList server
    (requires aria2, Transmission, or qBittorrent configured on the server).
  - `decompress_archive` — decompress archives (zip, rar, 7z, tar.gz, etc.) on the server.
  - `get_me` — get current authenticated user's profile.
  - `logout` — logout and invalidate the current authentication token.
  - `recursive_move` — recursively move an entire directory tree without listing individual file names.

### Changed
- Startup guide updated to list all 26 tools with categories.

## [0.2.5] — 2026-05-29

### Added
- **2FA/TOTP support**: `login()` tool accepts optional `otp_code` parameter for
  two-factor authentication.
- `upload_local_file` tool — upload a local file path directly without base64 encoding.
  Gated behind `OPENLIST_LOCAL_UPLOAD_ROOTS` environment variable.

### Changed
- Improved large file uploads: async chunked streaming (1MB chunks) instead of single `read_bytes()`.
- Write timeout increased to 120s.
- Version unification: `__version__` reads from package metadata at runtime.
  All version references consistent at v0.2.5.

### Fixed
- `validate_name()` now correctly allows filenames containing `..` patterns
  (e.g. `backup..tar.gz`, `..hidden_file`), only rejecting `.` and `..` as directory names.
- Installation guide corrected for source archive method.

### Security
- Base64 decode exception narrowed from `except Exception` to `(ValueError, binascii.Error)`.
- `OPENLIST_LOCAL_UPLOAD_ROOTS` restriction for local file uploads — disabled by default.

### Removed
- Automatic PyPI publishing from release workflow. Tag push creates a GitHub Release
  with build artifacts only.

## [0.2.4] — 2026-05-28

### Added
- **2FA / TOTP login support**: `login()` tool now accepts an optional `otp_code` parameter.
  When the OpenList account has 2FA enabled, the agent prompts the user for a TOTP code.

### Security
- HTTP warning for plain text credential transmission when using `http://` URLs.

## [0.2.3] — 2026-05-27

### Added
- `upload_local_file` tool (gated behind `OPENLIST_LOCAL_UPLOAD_ROOTS`).
- `OPENLIST_READONLY` environment variable — blocks all write/high-impact operations.
- `OPENLIST_ALLOWED_PATHS` environment variable — restricts MCP path operations to approved directories.
- Support for pagination parameters (`page`, `per_page`) in list operations.

### Security
- `upload_local_file` now requires explicit `OPENLIST_LOCAL_UPLOAD_ROOTS` configuration.
- HTTP transport warning when using plain `http://` URLs.

## [0.2.2] — 2026-05-26

### Fixed
- Version synchronization: all version strings (`pyproject.toml`, source, READMEs) now match.
- Various documentation inconsistencies resolved.

## [0.2.1] — 2026-05-26

### Added
- `.env` file support (via optional `python-dotenv` dependency).
- Verification command in documentation (`openlist-mcp`).
- Troubleshooting section in README.

### Changed
- Installation instructions overhauled: venv, source archive, verification steps.
- Documentation expanded with security notes, config file paths, and MCP client setup.

### Fixed
- Upload file path handling fix.
--Friendly startup message when `OPENLIST_URL` is not set.

## [0.2.0] — 2026-05-25

### Added
- MCP safety controls: `OPENLIST_READONLY`, `OPENLIST_ALLOWED_PATHS`.
- File management tools: `copy`, `move`, `remove`, `search_files`, `batch_rename`.
- Task management tools: `list_tasks`, `get_task_info`, `retry_task`, `cancel_task`, `delete_task`.
- Share management tools: `create_share`, `list_shares`, `cancel_share`, `delete_share`.
- Chinese documentation (`README-zh.md`).
- MIT License.

### Changed
- Split README into English (`README.md`) and Chinese (`README-zh.md`).

### Security
- JWT token auto-refresh on 401 responses.
- Path traversal prevention in `validate_path`.

## [0.1.0] — 2026-05-24

### Added
- Initial release.
- Core MCP server with basic file operations: `list_files`, `list_dirs`, `get_file_info`,
  `create_folder`, `rename`, `upload_file`, `get_download_url`.
- JWT authentication with automatic login.
- OpenList REST API client with `httpx`.
- MCP stdio server via `mcp[cli]` SDK.
- README with installation and configuration guide.

---

## Version history

| Version | Date | Highlights |
|---------|------|------------|
| 0.6.0 | 2026-10-07 | Dual mcp support (1.x and 2.x) via `_compat` import shim, `mcp` range widened to `<3.0.0`, upstream mcp 2.0 migration merged |
| 0.5.0 | 2026-08-16 | 107 tools: admin write for storages, offline-download clients and users; `delete_setting` query-param fix; runtime-derived banner counts |
| 0.4.1 | 2026-08-16 | Multipart resume via `X-File-Md5` identity proof, server-driven chunk slicing, live regression suites |
| 0.4.0 | 2026-06-14 | Share query-param fix, mcp<2 pin, multipart resumable upload, direct upload, manual scan, move tasks, allowlist gaps fixed |
| 0.3.3 | 2026-06-10 | _list_items import fix, _human_size dedup, import httpx moved to top |
| 0.3.2 | 2026-06-10 | Code audit fixes: enforce_writable gaps, delete_share params bug, mirror ordering, walker dedup |
| 0.3.1 | 2026-06-06 | OPENLIST_SKILLS, skills module, CI, tests, upgrade notice, confirm ⚠️, 401 fix |
| 0.2.12 | 2026-06-04 | SQLITE_BUSY retry, SSRF fix for magnet/ftp/sftp |
| 0.2.11 | 2026-06-04 | 79 tools: admin index/setting/user/meta/token tools |
| 0.2.10 | 2026-06-01 | 67 tools: batch ops, tree/disk_usage, mirror, admin read-only tools, torrent tools |
| 0.2.9 | 2026-06-01 | get_archive_meta, torrent_upload_parse, list_tasks(all), multipart_form() client helper |
| 0.2.8 | 2026-05-31 | Batch task ops, tree/disk_usage/find_duplicates/content_preview/mirror, read-only admin, torrent + SSH-key tools |
| 0.2.7 | 2026-05-30 | Auto TOTP, list_download_tools, validate_path fix |
| 0.2.6 | 2026-05-30 | offline_download, decompress_archive, get_me, logout, recursive_move |
| 0.2.5 | 2026-05-29 | 2FA/TOTP, upload_local_file, streaming uploads, release workflow |
| 0.2.4 | 2026-05-28 | 2FA login support, HTTP warning |
| 0.2.3 | 2026-05-27 | upload_local_file, READONLY, ALLOWED_PATHS |
| 0.2.2 | 2026-05-26 | Version sync and doc fixes |
| 0.2.1 | 2026-05-26 | .env support, doc overhaul |
| 0.2.0 | 2026-05-25 | Safety controls, file/task/share management tools |
| 0.1.0 | 2026-05-24 | Initial release |
