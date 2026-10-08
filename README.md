# OpenList MCP Server

<p align="center">
  <img src="docs/og-image.png" alt="OpenList MCP Server" width="800">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README-zh.md">中文</a>
</p>

<p align="center">
  <a href="https://github.com/hbestm/openlist-mcp-server/releases/latest"><img src="https://img.shields.io/github/v/release/hbestm/openlist-mcp-server?sort=semver&label=release" alt="Latest release"></a>
  <a href="https://github.com/hbestm/openlist-mcp-server/actions/workflows/ci.yml"><img src="https://github.com/hbestm/openlist-mcp-server/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/hbestm/openlist-mcp-server/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hbestm/openlist-mcp-server" alt="License"></a>
  <a href="https://github.com/hbestm/openlist-mcp-server/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
</p>

---

MCP Server for [OpenList](https://github.com/OpenListTeam/OpenList) — an open-source file management system (similar to Alist). Enables MCP-compatible AI agents to browse, upload, download, search, and manage files via the OpenList REST API.

```
┌────────────────┐     ┌────────────────────┐     ┌──────────────┐     ┌───────────────┐
│ Claude Desktop │────▶│ openlist-mcp-server │────▶│ OpenList API │────▶│ Storage (S3,  │
│   (or SOLO)    │ MCP │   (this project)    │ HTTP │   (your     │     │  SMB, Local,  │
└────────────────┘     └────────────────────┘     │   server)   │     │  ...)         │
                                                    └──────────────┘     └───────────────┘
```

## Features

| Category | Capabilities |
|----------|-------------|
| **Browse** | List directories, get file details, search files |
| **Manage** | Create/rename/delete files & folders, batch rename, regex rename, copy, move, recursive move, remove empty directories |
| **Transfer** | Upload base64 content, upload local files, get download URLs |
| **Share** | Create, update, enable, disable, cancel, delete share links |
| **Task** | List, retry, cancel, delete async tasks (offline downloads, copies, etc.) |
| **Torrent** | Parse `.torrent` files, generate torrents for existing files, rapid upload |
| **Auth** | Auto JWT login with TOTP/2FA support, automatic re-authentication on expiry |

**110 tools in total** — see the [Tools Reference](#tools-reference) below.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/hbestm/openlist-mcp-server.git
cd openlist-mcp-server
python3 -m venv venv
source venv/bin/activate    # Linux/macOS
# venv\Scripts\activate     # Windows
pip install -e .
```

### 2. Configure

Set these environment variables (or copy `.env.example` to `.env` and edit):

```bash
export OPENLIST_URL="https://your-openlist-instance.example.com"
export OPENLIST_USERNAME="your_username"
export OPENLIST_PASSWORD="your_password"
```

Optional safety controls:

```bash
export OPENLIST_READONLY="false"                          # Block all write operations
export OPENLIST_ALLOWED_PATHS="/mcp-dev-test,/public"     # Restrict to specific paths
export OPENLIST_LOCAL_UPLOAD_ROOTS="/tmp:/path/to/uploads" # Enable local file uploads
export OPENLIST_TOTP_SECRET="your_totp_secret"            # Auto-generate 2FA codes
export OPENLIST_ALLOW_HTTP="false"                        # Allow HTTP (insecure, use only on LAN)
export OPENLIST_SKILLS="core"                             # Tool groups: core(30), default(49), all(110)
```

**Choosing a tool tier.** Every tool schema stays resident in the agent's
context, so the tier is a standing cost on *every* model step, not a one-time
load:

| `OPENLIST_SKILLS` | Tools | ≈tokens/step | What it adds |
|---|---|---|---|
| `core` (default) | 30 | ~4.4k | `auth`, `fs`, `transfer` — browse, search, upload/download |
| `default` | 49 | ~6.5k | + `task`, `share` |
| `all` | 110 | ~14.7k | + `admin`, `advanced` — server management, archives, torrents |
| any group list | — | — | e.g. `fs,transfer,share` — combine the groups below |

For agent use, `core` or `default` is the right range. `fs/copy`, `fs/move` and
`fs/archive/decompress` run as **asynchronous tasks** on the server, so without
the `task` group an agent cannot tell whether they finished — that is what makes
`default` worth its extra ~2k tokens over `core`. Reserve `all` for when you
actually want server administration (storages, users, settings, metadata).

Groups and their sizes: `auth` (6), `fs` (16), `transfer` (8), `task` (11),
`share` (8), `admin` (42), `advanced` (16). Combine them with commas; a name that
is not one of these is ignored with a warning instead of failing the launch.


### 3. Verify

```bash
openlist-mcp
# Prints setup guide (no OPENLIST_URL) or starts MCP server (configured)
```

### 4. Add to Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openlist": {
      "command": "openlist-mcp",
      "env": {
        "OPENLIST_URL": "https://your-openlist-instance.example.com",
        "OPENLIST_USERNAME": "your_username",
        "OPENLIST_PASSWORD": "your_password"
      }
    }
  }
}
```

**Config file locations:** macOS: `~/Library/Application Support/Claude/` · Windows: `%APPDATA%\Claude\` · Linux: `~/.config/Claude/`

See [`mcp-config.example.json`](mcp-config.example.json) for a complete example with all optional settings.

Restart Claude Desktop, then try: *"List the files on my OpenList server."*

---

## Example Prompts

| Goal | Prompt |
|------|--------|
| Browse files | "List files in the root directory." |
| Search | "Search for files named 'report'." |
| Upload | "Upload this file to /documents." |
| Download | "Download https://example.com/file.zip to /downloads." |
| Batch rename | "Rename all .html files to .htm in /downloads." |
| Regex rename | "Remove numbers from filenames in /projects." |
| Clean up | "Delete all .tmp files, then remove empty folders." |
| Extract archive | "Extract data.zip to /downloads/data." |
| Download + extract | "Download this archive and extract it." |
| Create share | "Share this file with a password." |
| Update share | "Change the password on my share link." |
| Disable/enable share | "Temporarily disable this share." |
| Parse torrent | "What files are in this torrent?" |
| Generate torrent | "Create a torrent for myfile.iso." |
| Check identity | "What user am I logged in as?" |
| Check capabilities | "What can this MCP server do?" |

---

## Tools Reference

The groups below are the same ones `OPENLIST_SKILLS` selects from, and they are in
tier order: `core` is the first three, `default` adds `task` and `share`, and `all`
adds `admin` and `advanced`. Descriptions are the tools' own docstrings — the text
the model reads — so this table and the running server cannot drift apart.

<!-- BEGIN GENERATED: tools -->
### `auth` — 6 tools

In tiers: `core`, `default`, `all`.

| Tool | Description |
|------|-------------|
| `login` | Login to OpenList server using configured credentials. |
| `get_public_settings` | Get public settings of the OpenList server. |
| `list_my_ssh_keys` | List SSH public keys for the current user. |
| `add_ssh_key` | Add a new SSH public key for the current user. |
| `delete_ssh_key` | Delete an SSH public key by its ID. |
| `update_current_user` | Update the current user's profile (password, base path). |

### `fs` — 16 tools

In tiers: `core`, `default`, `all`.

| Tool | Description |
|------|-------------|
| `list_files` | List files and folders in a directory on OpenList. |
| `list_dirs` | List subdirectories under a directory. |
| `get_file_info` | Get detailed information about a specific file or folder. |
| `search_files` | Search for files and folders by keyword. |
| `create_folder` | Create a new folder (directory) on OpenList. |
| `rename` | Rename a file or folder. |
| `batch_rename` | Rename multiple files or folders in the same directory. |
| `regex_rename` | Rename files in a directory using regular expression substitution. |
| `copy` | Copy files or folders to another directory. |
| `move` | Move files or folders to another directory. |
| `remove` | Delete files or folders. |
| `remove_empty_dirs` | Recursively remove empty directories under the given path. |
| `recursive_move` | Recursively move an entire directory tree to a new location. |
| `tree` | Build a recursive directory tree for the given path. |
| `disk_usage` | Show disk usage summary for a directory. |
| `mirror` | Synchronize files from a source directory to a destination directory. |

### `transfer` — 8 tools

In tiers: `core`, `default`, `all`.

| Tool | Description |
|------|-------------|
| `get_download_url` | Get the download URL for a file on OpenList. |
| `upload_file` | Upload a file to OpenList from base64-encoded content. |
| `upload_file_multipart` | Upload a file using the resumable multipart upload API. |
| `upload_local_file` | Upload a local file that the MCP server process can access. |
| `multipart_upload_local_file` | Upload a local file via the resumable multipart API, streaming from disk. |
| `multipart_upload_status` | Query a multipart upload session's progress. |
| `multipart_abort_upload` | Abort a multipart upload session and discard its chunks. |
| `get_direct_upload_info` | Get client-side direct upload credentials for a storage backend. |

### `task` — 11 tools

In tiers: `default`, `all`.

| Tool | Description |
|------|-------------|
| `list_tasks` | List asynchronous tasks by OpenList task type and status. |
| `get_task_info` | Get one task by ID using OpenList's typed task API. |
| `delete_task` | Delete a completed or failed task. |
| `retry_task` | Retry a failed task. |
| `cancel_task` | Cancel a running task. |
| `batch_cancel_tasks` | Cancel multiple running tasks by ID. |
| `batch_delete_tasks` | Delete multiple completed or failed task records. |
| `batch_retry_tasks` | Retry multiple failed tasks by ID. |
| `clear_done_tasks` | Clear all completed, failed, and cancelled tasks of the given type. |
| `clear_succeeded_tasks` | Clear only successfully completed tasks. |
| `retry_failed_tasks` | Retry all failed tasks of the given type. |

### `share` — 8 tools

In tiers: `default`, `all`.

| Tool | Description |
|------|-------------|
| `create_share` | Create share link(s) for one or more files or folders. |
| `get_share_info` | Get detailed information about a specific share link. |
| `list_shares` | List all existing share links. |
| `update_share` | Update an existing share link's settings. |
| `cancel_share` | Cancel (disable) an existing share link, preventing further access. |
| `delete_share` | Delete a share link permanently. |
| `enable_share` | Enable a previously disabled/cancelled share link. |
| `disable_share` | Disable a share link temporarily without deleting it. |

### `admin` — 45 tools

In tiers: `all`.

| Tool | Description |
|------|-------------|
| `list_storages` | List all configured storage backends on the OpenList server. |
| `get_storage_info` | Get detailed information about a specific storage backend. |
| `create_storage` | Create a new storage backend (Admin only, irreversible-ish). |
| `update_storage` | Update an existing storage backend (Admin only). |
| `delete_storage` | Delete a storage backend and its configuration (Admin only). |
| `enable_storage` | Enable and remount an existing storage backend (Admin only). |
| `disable_storage` | Disable a storage backend without deleting it (Admin only). |
| `load_all_storages` | Reload/mount every enabled storage backend (Admin only). |
| `list_drivers` | List all registered storage driver names on the server. |
| `get_driver_info` | Get detailed information about a specific storage driver. |
| `list_drivers_detail` | List all storage drivers with full configuration templates. |
| `get_settings` | List all global settings on the OpenList server. |
| `get_setting` | Get a single global setting by its key. |
| `save_settings` | Update one or more global system settings. |
| `delete_setting` | Delete a custom setting by its key. |
| `set_aria2` | Configure the aria2 offline-download client (Admin only). |
| `set_qbittorrent` | Configure the qBittorrent offline-download client (Admin only). |
| `set_transmission` | Configure the Transmission offline-download client (Admin only). |
| `set_115` | Configure the 115 offline-download client (Admin only). |
| `set_115_open` | Configure the 115 Open offline-download client (Admin only). |
| `set_123_pan` | Configure the 123 Pan offline-download client (Admin only). |
| `set_123_open` | Configure the 123 Open offline-download client (Admin only). |
| `set_pikpak` | Configure the PikPak offline-download client (Admin only). |
| `set_thunder` | Configure the Thunder offline-download client (Admin only). |
| `set_thunderx` | Configure the ThunderX offline-download client (Admin only). |
| `set_thunder_browser` | Configure the Thunder Browser offline-download client (Admin only). |
| `set_guangyapan` | Configure the GuangYaPan offline-download client (Admin only). |
| `get_index_progress` | Get the current search index building progress. |
| `build_search_index` | Build the full-text search index for all storages. |
| `update_search_index` | Update the search index for specific paths. |
| `stop_indexing` | Stop the current search index building or updating operation. |
| `clear_search_index` | Delete all search index data. |
| `list_users` | List all user accounts on the server (Admin only). |
| `get_user` | Get detailed information about a specific user (Admin only). |
| `create_user` | Create a new OpenList user (Admin only). |
| `update_user` | Update an existing user (Admin only). |
| `list_metas` | List all metadata configurations on the server (Admin only). |
| `get_meta` | Get a specific metadata configuration by its ID (Admin only). |
| `create_meta` | Attach directory metadata to an OpenList path (Admin only). |
| `update_meta` | Update an existing metadata entry (Admin only). |
| `delete_meta` | Delete a metadata entry (Admin only). |
| `reset_api_token` | Reset the server API token (Admin only). |
| `start_manual_scan` | Start a one-off manual scan of a storage mount (Admin only). |
| `stop_manual_scan` | Stop a running manual scan (Admin only). |
| `get_manual_scan_progress` | Get the progress of the running (or last) manual scan (Admin only). |

### `advanced` — 16 tools

In tiers: `all`.

| Tool | Description |
|------|-------------|
| `get_capabilities` | Summarize this MCP server's OpenList capabilities and safety settings. |
| `offline_download` | Download a file from a remote URL directly to the OpenList server. |
| `batch_download` | Download multiple files from remote URLs at once. |
| `find_duplicates` | Find potentially duplicate files in a directory tree. |
| `content_preview` | Preview the first portion of a text file's content. |
| `get_archive_extensions` | Get the list of archive file extensions supported by the server. |
| `get_archive_meta` | Get metadata of an archive file without extracting it. |
| `decompress_archive` | Decompress an archive file (zip, rar, 7z, tar.gz, etc.) on the OpenList server. |
| `list_archive_files` | List files inside an archive without extracting it. |
| `get_me` | Get the current authenticated user's profile information. |
| `logout` | Logout from the OpenList server and invalidate the current token. |
| `list_download_tools` | List available offline download tools configured on this OpenList server. |
| `parse_torrent` | Parse a torrent file and return its contents (file list, metadata). |
| `torrent_upload_parse` | Upload and parse a torrent file via multipart form. |
| `generate_torrent` | Generate a .torrent file for an existing file on the OpenList server. |
| `torrent_rapid_upload` | Rapid upload (server-side import) from a torrent file. |
<!-- END GENERATED: tools -->

## Security

- **Use HTTPS in production** — credentials are transmitted in plain text over HTTP.
  HTTP is **rejected by default** — set `OPENLIST_ALLOW_HTTP=true` to enable (only for trusted LANs).
- **Use a dedicated low-privilege OpenList account** for MCP access. Avoid using the `admin` account for daily AI-agent operations.
- **Restrict storage scope** — do not expose system paths (home, Docker config, SSH keys, etc.) through OpenList.
- **Set `OPENLIST_READONLY=true`** to block all write/high-impact tools.
- **Set `OPENLIST_ALLOWED_PATHS`** to a comma-separated list to keep all path operations inside approved directories.
- **Protect your MCP config file**: `chmod 600 claude_desktop_config.json` (Linux/macOS).
- **Local file uploads are disabled by default** — explicitly set `OPENLIST_LOCAL_UPLOAD_ROOTS` to enable.
- **SSRF protection** — the `offline_download` tool resolves hostnames via DNS and blocks requests to private/internal IP ranges.
  Allowed URL schemes: `http://`, `https://`, `ftp://`, `sftp://` (SSRF checked), `magnet:` (exempt — no hostname).
- **Destructive operations** (`remove`, `delete_share`, `delete_task`, etc.) require `confirm=true` to prevent accidental data loss.

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| `OPENLIST_URL is required` | Env vars not set | Set `OPENLIST_URL`, `OPENLIST_USERNAME`, `OPENLIST_PASSWORD` |
| `password is incorrect` | Wrong credentials | Verify OpenList username and password |
| `Connection refused` | OpenList instance is down | Check that your OpenList server is running and reachable |
| Tool not found | PATH or venv issue | Re-activate venv or reinstall |
| MCP client "disconnected" | Claude Desktop needs restart | Restart after adding the server config |
| `search not available` | Search index disabled | Enable search in OpenList admin settings |
| `2FA code is required` | 2FA enabled on account | Call `login(otp_code="...")` with TOTP code, or set `OPENLIST_TOTP_SECRET` |
| `upload_local_file` rejected | `OPENLIST_LOCAL_UPLOAD_ROOTS` not set | Set the env var to allowed directories |
| `recursive_move` returns error | OpenList v4.2.x bug | MCP uses fallback (rename or move+rename) |
| Offline download stuck | aria2 not running on server | Start aria2 RPC daemon on the OpenList server |
| `list_download_tools` returns few tools | Download tools not configured | Install aria2, Transmission, etc. on the OpenList server |
| `URL points to private IP` | SSRF protection | Use a public URL instead of internal addresses |
| Non-JSON response | OpenList returns HTML | Use `get_task_info` with known task ID |
| HTTP warning | Using HTTP:// | Use HTTPS in production |

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

## License

MIT
