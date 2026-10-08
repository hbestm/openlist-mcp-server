# OpenList MCP Server — AI Agent Guide

> Copy this entire document and paste it to your AI assistant (Claude, etc.) to teach it how to install, configure, and use the OpenList MCP Server.

---

## Overview

OpenList MCP Server is a tool that lets AI agents manage files on an [OpenList](https://github.com/OpenListTeam/OpenList) instance. OpenList is a self-hosted file management platform that supports local storage, cloud drives (OneDrive, Google Drive, etc.), and more.

**110 tools available** across 9 categories:
- Browse: `list_files`, `list_dirs`, `get_file_info`, `search_files`
- Manage: `create_folder`, `rename`, `batch_rename`, `regex_rename`, `copy`, `move`, `remove`, `remove_empty_dirs`, `recursive_move`
- Transfer: `upload_file`, `upload_local_file`, `get_download_url`, `get_direct_upload_info`, `upload_file_multipart`, `multipart_upload_status`, `multipart_upload_local_file`, `multipart_abort_upload`
- Auth: `login`, `get_public_settings`, `get_me`, `get_capabilities`, `logout`
- Tasks: `list_tasks`, `get_task_info`, `retry_task`, `cancel_task`, `delete_task`, `batch_cancel_tasks`, `batch_delete_tasks`, `batch_retry_tasks`, `clear_done_tasks`, `clear_succeeded_tasks`, `retry_failed_tasks`
- Shares: `create_share`, `list_shares`, `get_share_info`, `update_share`, `enable_share`, `disable_share`, `cancel_share`, `delete_share`
- Smart: `tree`, `disk_usage`, `find_duplicates`, `content_preview`, `batch_download`, `mirror`
- System: `list_storages`, `get_storage_info`, `create_storage`, `update_storage`, `delete_storage`, `enable_storage`, `disable_storage`, `load_all_storages`, `list_drivers`, `get_driver_info`, `list_drivers_detail`, `get_settings`, `get_setting`, `save_settings`, `delete_setting`, `get_index_progress`, `build_search_index`, `update_search_index`, `stop_indexing`, `clear_search_index`, `start_manual_scan`, `stop_manual_scan`, `get_manual_scan_progress`, `list_users`, `get_user`, `create_user`, `update_user`, `list_metas`, `get_meta`, `create_meta`, `update_meta`, `delete_meta`, `reset_api_token`, `list_my_ssh_keys`, `add_ssh_key`, `delete_ssh_key`, `update_current_user`
- Advanced: `offline_download`, `set_aria2`, `set_qbittorrent`, `set_transmission`, `set_115`, `set_115_open`, `set_123_pan`, `set_123_open`, `set_pikpak`, `set_thunder`, `set_thunderx`, `set_thunder_browser`, `set_guangyapan`, `decompress_archive`, `get_archive_meta`, `list_archive_files`, `list_download_tools`, `get_archive_extensions`, `parse_torrent`, `torrent_upload_parse`, `generate_torrent`, `torrent_rapid_upload`

---

## For the Human: How to Install

Tell the user to follow these steps:

### 1. Prerequisites
- Python 3.10+
- An OpenList server (self-hosted, running and accessible)
- OpenList credentials with the permissions needed for the tools you plan to use

### 2. Install the MCP Server

```bash
# Option A: From GitHub
git clone https://github.com/hbestm/openlist-mcp-server.git
cd openlist-mcp-server
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Option B: From source archive
# Download ZIP from https://github.com/hbestm/openlist-mcp-server
unzip openlist-mcp-server-main.zip
cd openlist-mcp-server-main
pip install -e .
```

### 3. Verify

```bash
openlist-mcp
# Without OPENLIST_URL, this prints the setup guide and exits.
# With OPENLIST_URL configured, it starts the MCP stdio server.
```

### 4. Configure for Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openlist": {
      "command": "openlist-mcp",
      "env": {
        "OPENLIST_URL": "https://your-openlist.example.com",
        "OPENLIST_USERNAME": "admin",
        "OPENLIST_PASSWORD": "your_password",
        "OPENLIST_READONLY": "false",
        "OPENLIST_ALLOWED_PATHS": "",
        "OPENLIST_ALLOW_HTTP": "false",
        "OPENLIST_TOTP_SECRET": "your_totp_secret"
      }
    }
  }
}
```

> `OPENLIST_TOTP_SECRET` is optional — only needed if the OpenList account has 2FA enabled.

Linux: `~/.config/Claude/claude_desktop_config.json`
macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### 5. Optional: Enable local file uploads

```bash
export OPENLIST_LOCAL_UPLOAD_ROOTS="/tmp:/path/to/allowed/dirs"
```

### 6. Optional: Restrict AI access

```bash
export OPENLIST_READONLY="true"
export OPENLIST_ALLOWED_PATHS="/mcp-dev-test,/public"
```

`OPENLIST_READONLY=true` blocks write/high-impact tools. `OPENLIST_ALLOWED_PATHS`
restricts OpenList path operations to comma-separated path prefixes.

### 7. Optional: Enable aria2 for faster offline downloads

```bash
# On the OpenList server:
apt install aria2
aria2c --enable-rpc --rpc-listen-all=true --rpc-allow-origin-all -D
```

### 8. Optional: Auto 2FA with TOTP

If the OpenList account has 2FA enabled, set the TOTP secret so the MCP server generates codes automatically:

```bash
export OPENLIST_TOTP_SECRET="your_totp_secret_key"
```

No manual TOTP entry needed after this — the server handles it.

---

## For the AI: How to Use the Tools

### First Step: Always Login First

```python
# The MCP server auto-logs in on first API call.

# If 2FA is enabled and OPENLIST_TOTP_SECRET is configured,
# the TOTP code is generated automatically — no manual input needed.
# Just call login() without arguments:
login()

# If 2FA is enabled but no TOTP secret is configured,
# ask the user for their TOTP code:
login(otp_code="123456")
```

### File Operations

```python
# List files in a directory
list_files(path="/")

# Get details about a specific file or folder
get_file_info(path="/downloads/report.pdf")

# Search for files by keyword
search_files(parent="/", keywords="report")

# Create a folder
create_folder(path="/projects/new-project")

# Rename a file or folder
rename(path="/projects/old-name", name="new-name")

# Copy files to another directory
copy(src_dir="/photos", dst_dir="/backup/photos", names=["vacation.jpg", "family.png"])

# Move files to another directory
move(src_dir="/downloads", dst_dir="/archive", names=["file1.pdf", "file2.txt"])

# Delete files or folders (requires confirm=true)
remove(directory="/tmp", names=["old-file.txt"], confirm=True)

# Recursively move an entire directory tree
recursive_move(src_dir="/projects/old", dst_dir="/projects/new")

# Batch rename files in a directory
batch_rename(src_dir="/downloads", rename_objects=[
    {"src_name": "file1.txt", "new_name": "doc1.txt"},
    {"src_name": "file2.txt", "new_name": "doc2.txt"}
])

# Regex rename — rename files using Go-style regex patterns
# Use $1, $2 for capture groups (NOT \1 like Python/JS)
regex_rename(src_dir="/downloads", src_name_regex=r"(.*)\.html", new_name_regex=r"$1.htm")
regex_rename(src_dir="/photos", src_name_regex=r"^IMG_(\d+)", new_name_regex=r"photo_$1")

# Remove empty directories recursively (cleanup after bulk operations)
remove_empty_dirs(src_dir="/downloads", confirm=True)
```

> **Safety note**: `remove` requires `confirm=True`. The AI must explain what will be deleted and get user approval before passing `confirm=True`.

### File Transfer

```python
# Upload a file from a remote URL (server downloads it)
offline_download(url="https://example.com/file.pdf", path="/downloads")
# Default download tool is aria2. Specify a different tool:
offline_download(url="https://...", path="/downloads", tool="aria2")

# Upload file content from the conversation
upload_file(path="/docs", file_name="note.txt", file_content_base64="base64_encoded_content")

# Upload a file from the local machine (if enabled by admin)
upload_local_file(local_path="/home/user/report.pdf", remote_dir="/docs")

# Get a direct download URL for sharing
get_download_url(path="/shared/file.zip")
```

### Archive Operations

```python
# Decompress an archive (zip, rar, 7z, tar.gz, etc.)
decompress_archive(
    src_dir="/downloads",
    names="data.zip",
    dst_dir="/downloads/data",
    overwrite=True,
    put_into_new_dir=True
)
```

### Download Tools

```python
# List available download tools on the OpenList server
list_download_tools()
# Returns: ["aria2", "Transmission", "qBittorrent", ...]

# Download with a specific tool
offline_download(url="https://example.com/file.iso", path="/downloads", tool="Transmission")
offline_download(url="https://example.com/file.zip", path="/downloads", tool="qBittorrent")
```

### Authentication

```python
# Login (auto-handled, only use for explicit re-login or 2FA)
login(otp_code="")  # Provide TOTP code if 2FA is enabled

# Get current user info (check your identity and permissions)
get_me()

# Get public server settings
get_public_settings()

# Logout (invalidate current token)
logout()
```

### Task Management

```python
# List typed async tasks when the OpenList deployment exposes list endpoints
list_tasks(task_type="offline_download", status="undone")
list_tasks(task_type="offline_download", status="done")

# Get one task by ID. This is the most reliable way to check a task returned by offline_download.
get_task_info(task_id="task_id_here", task_type="offline_download")

# Retry a failed task
retry_task(task_id="task_id_here", task_type="offline_download")

# Cancel a running task
cancel_task(task_id="task_id_here", task_type="offline_download", confirm=True)

# Delete a task record
delete_task(task_id="task_id_here", task_type="offline_download", confirm=True)
```

### Share Management

```python
# Create a share link for one or more files or folders
# NOTE: files is a list, not a single path string
create_share(files=["/docs/report.pdf", "/docs/summary.csv"], pwd="optional_password")

# List all existing share links
list_shares()

# Get details about a specific share
get_share_info(share_id="abc123")

# Update an existing share (password, expiration, files)
update_share(share_id="abc123", pwd="new_password",
             files=["/docs/report.pdf", "/docs/summary.csv"])

# Temporarily disable a share (can be re-enabled later)
disable_share(share_id="abc123")

# Re-enable a disabled share
enable_share(share_id="abc123")

# Cancel (disable) a share (alias for disable_share)
cancel_share(share_id="abc123", confirm=True)

# Permanently delete a share link
delete_share(share_id="abc123", confirm=True)
```

### Torrent Operations

```python
# Generate a .torrent file for an existing file on the server
generate_torrent(path="/downloads/myfile.iso")
# Returns: { "file_name": "myfile.iso.torrent", "info_hash": "...", "torrent_data": "<base64>" }

# Parse a torrent file to see its contents (pass base64-encoded torrent data)
parse_torrent(torrent_data="ZDc6Y29tbWVud...")
# Returns: { "name": "...", "total_size": ..., "files": [...] }

# Attempt rapid upload from a torrent (requires CAS-capable storage)
torrent_rapid_upload(torrent_data="ZDc6Y29tbWVud...", path="/downloads")
```

> **Note**: `torrent_rapid_upload` requires the storage backend to support CAS (Content Addressable
> Storage). Local storage typically does not support CAS. The tool will return a clear message
> if CAS is unavailable.

### Batch Task Operations

```python
# Cancel multiple tasks at once (requires confirm)
batch_cancel_tasks(task_ids=["id1", "id2"], task_type="offline_download", confirm=True)

# Delete multiple task records
batch_delete_tasks(task_ids=["id1", "id2"], task_type="offline_download", confirm=True)

# Retry multiple failed tasks
batch_retry_tasks(task_ids=["id1", "id2"], task_type="offline_download")

# Clear all completed/failed/cancelled tasks at once
clear_done_tasks(task_type="offline_download")

# Clear only successfully completed tasks (keeps failed for inspection)
clear_succeeded_tasks(task_type="offline_download")

# Retry every failed task of a type
retry_failed_tasks(task_type="offline_download")
```

### Smart Tools

```python
# Build a recursive directory tree
tree(path="/", max_depth=3)
# Returns:
# 📁 / (root)
# ├── 📁 downloads/
# │   ├── 📄 file.zip (1.2 MB)
# │   └── 📁 data/
# └── 📄 readme.txt

# Show disk usage summary by directory and file type
disk_usage(path="/")
# Returns JSON with top directories, counts, file type breakdown

# Find potential duplicate files (by name+size or size only)
find_duplicates(path="/", by="name_size")
# Returns JSON grouped by criteria, shows duplicate groups

# Preview text file content without full download
content_preview(path="/downloads/log.txt", max_chars=5000)

# Batch download multiple URLs at once
batch_download(urls=["https://example.com/a.zip", "https://example.com/b.zip"],
               path="/downloads", tool="aria2")

# Sync a directory — dry run first
mirror(src_dir="/source", dst_dir="/backup", mode="push", dry_run=True)
mirror(src_dir="/source", dst_dir="/backup", mode="pull", dry_run=True)
# Then execute
mirror(src_dir="/source", dst_dir="/backup", mode="mirror", dry_run=False)
```

### System (Read-Only Admin)

```python
# List all storage backends
list_storages()

# Get details about a specific storage
get_storage_info(storage_id=2)

# List all available storage drivers
list_drivers()

# Get driver configuration fields
get_driver_info(driver="Local")

# View all server settings
get_settings()

# View a single setting
get_setting(key="site_title")

# Check search index progress
get_index_progress()

# Manage SSH keys
list_my_ssh_keys()
add_ssh_key(title="my-laptop", public_key="ssh-rsa AAA...")
delete_ssh_key(key_id=1, confirm=True)

# Update current user (password or base path)
update_current_user(old_password="current", password="newpassword")
update_current_user(base_path="/restricted-path")
```

---

## Quick Prompt Examples

Copy and paste these prompts to your AI assistant:

| What you want to do | Say to the AI |
|--------------------|--------------|
| **下载文件** | "帮我把这个文件下载到 downloads 目录：https://example.com/file.zip" |
| **用指定工具下载** | "用 Transmission 下载这个 BT 链接：magnet:?xt=..." |
| **查可用的下载工具** | "看看我这个服务器上有哪些下载工具可以用" |
| **BT 下载** | "帮我把这个种子下载下来" |
| **解析种子** | "这个种子文件里都有什么文件？" |
| **生成种子** | "为 /downloads/myfile.iso 生成一个种子文件" |
| **解压文件** | "把 downloads 目录下的 data.zip 解压到 data 文件夹" |
| **下载+解压** | "把这个压缩包下载下来然后解压到项目目录" |
| **批量重命名** | "把 downloads 目录里所有 .html 改成 .htm" |
| **正则重命名** | "用正则去掉 /projects 下文件名中的数字" |
| **批量清理** | "把 downloads 目录里所有 .tmp 文件删掉，再清理空文件夹" |
| **创建分享** | "把这个文件分享给别人" |
| **修改分享密码** | "把我的分享链接密码改一下" |
| **停用/启用分享** | "暂时停用这个分享，等会再打开" |
| **查自己是谁** | "我现在是以什么身份登录的？" |
| **查存储空间** | "看看我这个 OpenList 服务器上挂载了哪些存储" |
| **查存储详情** | "看看我第一个存储还剩多少空间" |
| **查服务器设置** | "帮我看一下这个服务器的配置" |
| **改密码** | "帮我把我的 OpenList 密码改了" |

## Common Workflows (AI Recommendations)

### Workflow 1: Download + Extract Archive

When the user says "download this dataset and extract it":

```python
# Step 1: Offline download the archive
offline_download(url="https://example.com/dataset.zip", path="/downloads")
# Inform the user: "I've started downloading the archive. It will be saved to /downloads."

# Step 2: Wait for download to complete. Use the task ID returned by offline_download.
get_task_info(task_id="task_id_here", task_type="offline_download")

# Step 3: Decompress
decompress_archive(
    src_dir="/downloads",
    names="dataset.zip",
    dst_dir="/downloads/dataset",
    put_into_new_dir=True
)
```

### Workflow 2: Organize Files

When the user says "clean up my downloads folder":

```python
# Step 1: List the directory
files = list_files(path="/downloads")

# Step 2: Identify files to organize (by date, type, etc.)
# Step 3: Move or remove as appropriate
move(src_dir="/downloads", dst_dir="/archive/2024", names=["old_report.pdf"])

# For large directories, use recursive_move
recursive_move(src_dir="/downloads/messy-folder", dst_dir="/organized/messy-folder")
```

### Workflow 3: Share Files

When the user says "share this file with someone":

```python
# Step 1: Create a share link (note: files is a list)
share = create_share(files=["/shared/report.pdf"], pwd="optional_pass")
# Step 2: Inform the user of the share link and password
# "Here's your share link: https://your-openlist.com/s/abc123"
```

### Workflow 4: Share Lifecycle (Update/Disable/Re-enable)

When the user says "change the password on my share" or "temporarily disable it":

```python
# Update password
update_share(share_id="abc123", pwd="new_password",
             files=["/shared/report.pdf"])

# Disable (temporarily)
disable_share(share_id="abc123")

# Re-enable later
enable_share(share_id="abc123")

# Permanently delete
delete_share(share_id="abc123", confirm=True)
```

### Workflow 5: Torrent Operations

When the user says "what's in this torrent?" or "generate a torrent for this file":

```python
# Parse a torrent file (from base64 content)
info = parse_torrent(torrent_data="<base64_encoded_torrent>")
# "This torrent contains: video.mp4 (2.3 GB), cover.jpg (150 KB)"

# Generate a torrent
result = generate_torrent(path="/downloads/myfile.iso")
# "Generated torrent: myfile.iso.torrent (info_hash: abc123...)"
```

---

## Important Notes

1. **Not all features work on all OpenList versions.** OpenList v4.2.2 has a bug where `POST /api/fs/recursive_move` returns an error. The MCP server automatically falls back to `rename` (same directory) or `move` + `rename` (cross-directory) on affected versions.

2. **`search_files` requires search indexing to be enabled** on the OpenList server. If search is disabled, the tool returns a 404.

3. **`offline_download`** supports multiple download tools: `aria2` (default, supports https/http/magnet), `Transmission` (BitTorrent/HTTP), `qBittorrent` (BitTorrent/HTTP), and `SimpleHttp` (http only, may not work on all versions). Run `list_download_tools` to see what's available on the server.

4. **`upload_local_file` is DISABLED by default.** It requires the admin to set `OPENLIST_LOCAL_UPLOAD_ROOTS` environment variable.

5. **All paths start with `/`**, representing the OpenList storage root. The actual filesystem path depends on the storage backend configuration.

6. **The `names` parameter** in `copy`, `move`, and `remove` accepts both a comma-separated string (`"file1.txt,file2.pdf"`) and a JSON array of strings.

7. **Token expiry is handled automatically.** The server re-logs in when it receives a 401 response.

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| "Login failed: invalid username or password" | Wrong credentials | Ask the user to verify OPENLIST_USERNAME and OPENLIST_PASSWORD |
| "Connection refused" | OpenList server not running | Ask the user to start their OpenList server |
| "Tool not found" when calling offline_download | Selected tool not configured on OpenList server | Run `list_download_tools` to see available tools; install missing ones on the server |
| "Auto-generated TOTP code was rejected" | Wrong OPENLIST_TOTP_SECRET value | Ask the user to verify the TOTP secret in their authenticator app |
| "search not available" | Search indexing disabled | Inform the user, suggest enabling search in OpenList settings |
| "object not found" on recursive_move | OpenList v4.2.x may not support the native recursive move endpoint | The MCP server attempts fallback with rename or move + rename; report any fallback error to the user |
| "upload_local_file" rejected | OPENLIST_LOCAL_UPLOAD_ROOTS not set | Ask the user to set the env var to allowed directories |
| ".env" file not loading | python-dotenv not installed | Ask the user to run `pip install python-dotenv` |
| Offline download task stuck | aria2 RPC not running on the server | Ask the user to start aria2 RPC daemon on the OpenList server |
| "Guest user is disabled" | Token expired or invalid | The server will auto-re-login on next API call — no action needed |
| Transmission/qBittorrent not working | Download tool not properly configured | Check port, credentials, and service status on the OpenList server |
| "URL points to a private/internal IP address" | SSRF protection blocked the URL | The `offline_download` tool blocks downloads from private IP ranges (127.x, 10.x, 192.168.x, etc.) for security. Use a public URL instead. |
| HTTP warning about plain text | Using HTTP instead of HTTPS | Inform user to use HTTPS in production; safe on local network |
