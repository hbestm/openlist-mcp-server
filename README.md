# OpenList MCP Server

<p align="center">
  <img src="docs/og-image.png" alt="OpenList MCP Server" width="800">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README-zh.md">中文</a>
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

**107 tools in total** — see the [Tools Reference](#tools-reference) below.

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
export OPENLIST_SKILLS="core"                             # Tool groups: core(30), default(49), all(107)
```

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

### Auth & Public

| Tool | Description |
|------|-------------|
| `login` | Login using configured credentials. If 2FA is enabled and `OPENLIST_TOTP_SECRET` is set, TOTP is auto-generated. Otherwise pass `otp_code` manually. |
| `get_public_settings` | Get public OpenList settings without authentication. |
| `get_me` | Get current user profile (username, role, permissions, 2FA status). |
| `get_capabilities` | Summarize server settings, current user, available download tools, and MCP safety config. |
| `logout` | Invalidate the current token. |

### File System

| Tool | Description |
|------|-------------|
| `list_files` | List files and folders in a directory (supports pagination). |
| `list_dirs` | List child directories under a path (useful for destination selection). |
| `get_file_info` | Get detailed info for a file or folder (size, type, provider, raw_url). |
| `search_files` | Search files by keyword (requires search index on OpenList). |
| `create_folder` | Create a new directory. |
| `rename` | Rename a file or folder. |
| `batch_rename` | Rename multiple files/folders in the same directory. |
| `regex_rename` | Batch rename using Go-style regex patterns (`$1`, `$2` for capture groups). |
| `copy` | Copy files/folders to another directory. |
| `move` | Move files/folders to another directory. |
| `remove` | Delete files/folders. Requires `confirm=true`. |
| `remove_empty_dirs` | Recursively remove empty directories (useful after cleanup). |
| `recursive_move` | Move an entire directory tree (with fallback for OpenList v4.2.x). |

### Transfer

| Tool | Description |
|------|-------------|
| `get_download_url` | Get direct/proxy download URL for a file. |
| `upload_file` | Upload base64-encoded file content (max 100 MB). |
| `upload_file_multipart` | Upload base64 content via the resumable multipart API (large files, resumable). Requires an OpenList build with the multipart API (master after v4.2.5). |
| `upload_local_file` | Upload a local file path readable by the MCP server. Disabled by default; set `OPENLIST_LOCAL_UPLOAD_ROOTS` to enable. |
| `multipart_upload_local_file` | Stream a local file to the server via the resumable multipart API without loading it into memory. |
| `multipart_upload_status` | Query a multipart upload session's progress (by upload_id or path+size). |
| `multipart_abort_upload` | Abort a multipart upload session and discard its chunks. Requires `confirm=true`. |
| `get_direct_upload_info` | Get client-side direct upload credentials for storage backends that support it (S3, etc.). |

### Task Management

| Tool | Description |
|------|-------------|
| `list_tasks` | List async tasks by type (`offline_download`, `upload`, `copy`, etc.) and status (`done`, `undone`). |
| `get_task_info` | Get a single task by ID — the most reliable way to inspect a task. |
| `retry_task` | Retry a failed task. |
| `cancel_task` | Cancel a running task. Requires `confirm=true`. |
| `delete_task` | Delete a task record. Requires `confirm=true`. |
| `batch_cancel_tasks` | Cancel multiple tasks at once by ID. Requires `confirm=true`. |
| `batch_delete_tasks` | Delete multiple task records by ID. Requires `confirm=true`. |
| `batch_retry_tasks` | Retry multiple failed tasks by ID. |
| `clear_done_tasks` | Clear all completed/failed/cancelled tasks of a type. |
| `clear_succeeded_tasks` | Clear only successfully completed tasks. |
| `retry_failed_tasks` | Retry every failed task of a type in one shot. |

### Share Management

| Tool | Description |
|------|-------------|
| `create_share` | Create share link(s) for one or more files/folders. Pass `files: list[str]`. |
| `list_shares` | List all existing share links. |
| `get_share_info` | Get details of a specific share link by ID. |
| `update_share` | Modify an existing share (password, expiration, files, etc.). |
| `enable_share` | Re-enable a disabled share link. |
| `disable_share` | Temporarily disable a share link without deleting it. |
| `cancel_share` | Alias for `disable_share`. |
| `delete_share` | Permanently delete a share link. Requires `confirm=true`. |

### System (Admin)

| Tool | Description |
|------|-------------|
| `list_storages` | List all configured storage backends (mount path, driver, status, space). |
| `get_storage_info` | Get detailed info about a specific storage by ID. |
| `list_drivers` | List all registered storage driver names. |
| `get_driver_info` | Get details about a specific storage driver. |
| `list_drivers_detail` | List all drivers with full configuration templates. |
| `get_settings` | List all global server settings. |
| `get_setting` | Get a single setting by key (e.g. `site_title`). |
| `save_settings` | Update one or more global settings atomically. Requires `confirm=true`. |
| `delete_setting` | Remove a custom setting. Requires `confirm=true`. |
| `get_index_progress` | Get search index building progress. |
| `build_search_index` | Trigger full search index rebuild. Requires `confirm=true`. |
| `update_search_index` | Trigger incremental search index update. Requires `confirm=true`. |
| `stop_indexing` | Stop the current indexing process. Requires `confirm=true`. |
| `clear_search_index` | Clear the entire search index. Requires `confirm=true`. |
| `list_users` | List all user accounts with pagination. |
| `get_user` | Get detailed info for a specific user by ID. |
| `list_metas` | List all metadata configurations. |
| `get_meta` | Get metadata details by ID. |
| `reset_api_token` | Generate a new API token. Requires `confirm=true`. |
| `start_manual_scan` | Start a one-off manual scan of a storage mount. Requires `confirm=true`. |
| `stop_manual_scan` | Stop a running manual scan. Requires `confirm=true`. |
| `get_manual_scan_progress` | Get the progress of the running/last manual scan. |
| `list_my_ssh_keys` | List SSH public keys for the current user. |
| `add_ssh_key` | Add a new SSH public key. Respects `OPENLIST_READONLY`. |
| `delete_ssh_key` | Delete an SSH public key by ID. Requires `confirm=true`. |
| `update_current_user` | Update current user's password or base path. |

### Smart Tools

| Tool | Description |
|------|-------------|
| `tree` | Build a recursive directory tree with 📁/📄 icons (configurable depth). |
| `disk_usage` | Show disk usage summary by directory and file type. |
| `find_duplicates` | Find potential duplicate files grouped by name+size or size only. |
| `content_preview` | Preview text file content via range request (no full download). |
| `batch_download` | Download multiple URLs at once via offline download. |
| `mirror` | Recursive directory sync — compare src/dst, copy missing files, optionally delete extras. Modes: `push` (src→dst), `pull` (dst→src), `mirror` (push + delete extras in dst). |

### Advanced & Torrent

| Tool | Description |
|------|-------------|
| `offline_download` | Download a file from a remote URL directly to the OpenList server. Supports `http://`, `https://`, `magnet:`, `ftp://`, and `sftp://` URLs. Uses aria2, Transmission, or qBittorrent. Blocks private/internal IPs (SSRF protection). Magnet links are exempt from SSRF check (no hostname to resolve). |
| `decompress_archive` | Decompress archives (zip, rar, 7z, tar.gz, etc.) on the server. |
| `get_archive_meta` | Get archive metadata (format, encryption, comment, file tree) without extracting. |
| `list_archive_files` | List files inside an archive without extracting. |
| `torrent_upload_parse` | Upload and parse a `.torrent` file via multipart form, returns info + reusable base64 data. |
| `list_download_tools` | List available download tools configured on the OpenList server. |
| `get_archive_extensions` | List archive file extensions supported by the server. |
| `parse_torrent` | Parse a `.torrent` file (base64) and return file list and metadata. |
| `generate_torrent` | Generate a `.torrent` file for an existing file on the server. |
| `torrent_rapid_upload` | Attempt server-side rapid import from torrent data (requires CAS-capable storage). |

---

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
