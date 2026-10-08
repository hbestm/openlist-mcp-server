# OpenList MCP Server 中文

<p align="center">
  <img src="docs/og-image.png" alt="OpenList MCP Server" width="800">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README-zh.md">中文</a>
</p>

<p align="center">
  <a href="https://github.com/hbestm/openlist-mcp-server/releases/latest"><img src="https://img.shields.io/github/v/release/hbestm/openlist-mcp-server?sort=semver&label=release" alt="最新版本"></a>
  <a href="https://github.com/hbestm/openlist-mcp-server/actions/workflows/ci.yml"><img src="https://github.com/hbestm/openlist-mcp-server/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/hbestm/openlist-mcp-server/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hbestm/openlist-mcp-server" alt="License"></a>
  <a href="https://github.com/hbestm/openlist-mcp-server/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
</p>

---

[OpenList](https://github.com/OpenListTeam/OpenList) 的 MCP 服务端。OpenList 是一个开源的文件管理系统（类似 Alist）。本服务让 MCP 协议兼容的 AI 智能体（Claude、SOLO 等）通过 OpenList REST API 浏览、上传、下载、搜索和管理文件。

```
┌────────────────┐     ┌────────────────────┐     ┌──────────────┐     ┌───────────────┐
│ Claude Desktop │────▶│ openlist-mcp-server │────▶│ OpenList API │────▶│ 存储后端 (S3, │
│   (或 SOLO)    │ MCP │   (本项目)          │ HTTP │   (你的服务器)│     │  SMB, 本地,   │
└────────────────┘     └────────────────────┘     └──────────────┘     │  ...)         │
                                                                        └───────────────┘
```

## 功能特性

| 分类 | 能力 |
|------|------|
| **浏览** | 列出目录、文件详情、搜索文件 |
| **管理** | 创建/重命名/删除文件目录、批量重命名、正则重命名、复制、移动、递归移动、清理空目录 |
| **传输** | Base64 上传、本地文件上传、获取下载链接 |
| **分享** | 创建、更新、启用、禁用、取消、删除分享链接 |
| **任务** | 查看、重试、取消、删除异步任务（离线下载、复制等） |
| **Torrent** | 解析 .torrent 文件、为已有文件生成种子、秒传 |
| **认证** | 自动 JWT 登录（支持 TOTP/2FA）、过期自动重登 |

**共 110 个工具** — 详见下方[工具参考](#工具参考)。

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/hbestm/openlist-mcp-server.git
cd openlist-mcp-server
python3 -m venv venv
source venv/bin/activate    # Linux/macOS
# venv\Scripts\activate     # Windows
pip install -e .
```

### 2. 配置

设置环境变量（或复制 `.env.example` 为 `.env` 后编辑）：

```bash
export OPENLIST_URL="https://你的-openlist-地址.com"
export OPENLIST_USERNAME="你的用户名"
export OPENLIST_PASSWORD="你的密码"
```

可选安全控制：

```bash
export OPENLIST_READONLY="false"                           # 禁止所有写入操作
export OPENLIST_ALLOWED_PATHS="/mcp-dev-test,/public"      # 限制可操作的路径
export OPENLIST_LOCAL_UPLOAD_ROOTS="/tmp:/允许的目录"      # 启用本地文件上传
export OPENLIST_TOTP_SECRET="你的_totp_密钥"               # 自动生成 2FA 验证码
export OPENLIST_ALLOW_HTTP="false"                         # 允许 HTTP（不安全，仅局域网使用）
export OPENLIST_SKILLS="core"                              # 工具组: core(30个), default(49个), all(110个)
```

**工具档位怎么选。** 工具 schema 是**每一步模型请求都要常驻**的上下文，不是一次性的加载开销：

| `OPENLIST_SKILLS` | 工具数 | ≈tokens/步 | 增加了什么 |
|---|---|---|---|
| `core`（默认） | 30 | ~4.4k | `auth`、`fs`、`transfer` —— 浏览、搜索、上传下载 |
| `default` | 49 | ~6.5k | 再加 `task`、`share` |
| `all` | 110 | ~14.7k | 再加 `admin`、`advanced` —— 服务器管理、压缩包、种子 |
| 任意组名组合 | — | — | 例如 `fs,transfer,share`，从下表里挑 |

**给 agent 用，`core` 或 `default` 是合适区间。** `fs/copy`、`fs/move`、`fs/archive/decompress` 在服务端是**异步任务**，没有 `task` 组 agent 就无法确认它们是否真的完成 —— 这就是 `default` 比 `core` 多花约 2k tokens 换来的东西。`all` 留给确实需要做服务器管理的场景（存储、用户、设置、元数据）。

各组与规模：`auth`(6)、`fs`(16)、`transfer`(8)、`task`(11)、`share`(8)、`admin`(42)、`advanced`(16)。用逗号组合；不属于这 7 个的名字会被**忽略并告警**，而不是让启动失败。


### 3. 验证

```bash
openlist-mcp
# 未设置 OPENLIST_URL 时打印配置引导，已配置则启动 MCP 服务
```

### 4. 添加到 Claude Desktop

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "openlist": {
      "command": "openlist-mcp",
      "env": {
        "OPENLIST_URL": "https://你的-openlist-地址.com",
        "OPENLIST_USERNAME": "你的用户名",
        "OPENLIST_PASSWORD": "你的密码"
      }
    }
  }
}
```

**配置文件位置：** macOS: `~/Library/Application Support/Claude/` · Windows: `%APPDATA%\Claude\` · Linux: `~/.config/Claude/`

完整示例（含所有可选配置）见 [`mcp-config.example.json`](mcp-config.example.json)。

重启 Claude Desktop，试试说：*"列出我 OpenList 上的文件。"*

---

## 快速上手 Prompt 示例

| 目标 | Prompt |
|------|--------|
| 浏览文件 | "列出根目录的文件。" |
| 搜索文件 | "搜索包含'报告'的文件。" |
| 上传文件 | "把这个文件上传到 /documents。" |
| 下载文件 | "把 https://example.com/file.zip 下载到 /downloads。" |
| 批量重命名 | "把 downloads 下所有 .html 改成 .htm。" |
| 正则重命名 | "用正则去掉 /projects 下文件名中的数字。" |
| 清理 | "删除所有 .tmp 文件然后清理空文件夹。" |
| 解压 | "把 data.zip 解压到 /downloads/data。" |
| 下载+解压 | "下载这个压缩包并解压。" |
| 创建分享 | "把这个文件分享给别人，加个密码。" |
| 修改分享 | "把我的分享链接密码改一下。" |
| 停用/启用分享 | "暂时停用这个分享。" |
| 解析种子 | "这个种子文件里有什么？" |
| 生成种子 | "为 myfile.iso 生成种子文件。" |
| 查身份 | "我现在以什么身份登录？" |
| 查能力 | "这个 MCP 服务器能做什么？" |

---

## 工具参考

下列分组就是 `OPENLIST_SKILLS` 所选择的那些组，且按档位顺序排列：`core` 是前三组，`default` 再加 `task` 与 `share`，`all` 再加 `admin` 与 `advanced`。描述取自工具自身的 docstring（即模型实际读到的文本），因此本表与运行中的服务不会脱节。

<!-- BEGIN GENERATED: tools -->
### `auth` — 认证(6 个工具)

属于 `core`, `default`, `all` 档。

| 工具 | 说明 |
|------|------|
| `login` | 使用配置的凭据登录。如果设置 `OPENLIST_TOTP_SECRET`，TOTP 自动生成；否则需传 `otp_code`。 |
| `get_public_settings` | 获取 OpenList 公共设置（无需认证）。 |
| `list_my_ssh_keys` | 列出当前用户的 SSH 公钥。 |
| `add_ssh_key` | 添加新的 SSH 公钥。受 `OPENLIST_READONLY` 保护。 |
| `delete_ssh_key` | 按 ID 删除 SSH 公钥。需要 `confirm=true`。 |
| `update_current_user` | 修改当前用户密码或基础路径。 |

### `fs` — 文件系统(16 个工具)

属于 `core`, `default`, `all` 档。

| 工具 | 说明 |
|------|------|
| `list_files` | 列出目录中的文件和文件夹（支持分页）。 |
| `list_dirs` | 列出子目录（适合用作目标路径选择）。 |
| `get_file_info` | 获取文件或文件夹详情（大小、类型、存储提供商、直链）。 |
| `search_files` | 按关键字搜索文件（需 OpenList 启用搜索索引）。 |
| `create_folder` | 创建目录。 |
| `rename` | 重命名文件或文件夹。 |
| `batch_rename` | 批量重命名同一目录下的多个文件/文件夹。 |
| `regex_rename` | 用 Go 风格正则批量重命名（`$1`、`$2` 引用捕获组）。 |
| `copy` | 复制文件/文件夹到另一目录。 |
| `move` | 移动文件/文件夹到另一目录。 |
| `remove` | 删除文件/文件夹。需 `confirm=true`。 |
| `remove_empty_dirs` | 递归删除空目录（清理后收尾）。 |
| `recursive_move` | 递归移动整个目录树（兼容 OpenList v4.2.x fallback）。 |
| `tree` | 递归生成目录树（带 📁/📄 图标）。 |
| `disk_usage` | 按目录和文件类型统计磁盘用量。 |
| `mirror` | 递归目录同步 — 比较源/目标目录，复制缺失文件，可选删除多余文件。模式：`push`（src→dst）、`pull`（dst→src）、`mirror`（push + 删除 dst 中多余文件）。 |

### `transfer` — 传输(8 个工具)

属于 `core`, `default`, `all` 档。

| 工具 | 说明 |
|------|------|
| `get_download_url` | 获取文件下载直链或代理链接。 |
| `upload_file` | 通过 base64 上传文件内容（最大 100MB）。 |
| `upload_file_multipart` | 通过可续传的 multipart 分块 API 上传 base64 内容（支持大文件、断点续传）。需 OpenList v4.2.5+ 且开启 `multipart_enabled` 设置。 |
| `upload_local_file` | 上传 MCP 服务器可读取的本地文件。默认禁用，需设 `OPENLIST_LOCAL_UPLOAD_ROOTS`。 |
| `multipart_upload_local_file` | 通过可续传的 multipart API 流式上传本地文件，不占用内存。 |
| `multipart_upload_status` | 查询 multipart 上传会话进度（按 upload_id 或 path+size）。 |
| `multipart_abort_upload` | 中止 multipart 上传会话并丢弃分块。需 `confirm=true`。 |
| `get_direct_upload_info` | 获取支持直传的后端（S3 等）的客户端直传凭据。 |

### `task` — 任务(11 个工具)

属于 `default`, `all` 档。

| 工具 | 说明 |
|------|------|
| `list_tasks` | 按类型和状态列出异步任务。 |
| `get_task_info` | 按 ID 查询单个任务。 |
| `delete_task` | 删除任务记录。需 `confirm=true`。 |
| `retry_task` | 重试失败的任务。 |
| `cancel_task` | 取消正在运行的任务。需 `confirm=true`。 |
| `batch_cancel_tasks` | 按 ID 批量取消任务。需 `confirm=true`。 |
| `batch_delete_tasks` | 按 ID 批量删除任务记录。需 `confirm=true`。 |
| `batch_retry_tasks` | 按 ID 批量重试失败任务。 |
| `clear_done_tasks` | 清除所有已完成/失败/取消的任务。 |
| `clear_succeeded_tasks` | 仅清除成功完成的任务。 |
| `retry_failed_tasks` | 一键重试所有失败任务。 |

### `share` — 分享(8 个工具)

属于 `default`, `all` 档。

| 工具 | 说明 |
|------|------|
| `create_share` | 创建分享链接，传 `files: list[str]`（支持多文件）。 |
| `get_share_info` | 按 ID 查看单个分享详情。 |
| `list_shares` | 列出所有分享链接。 |
| `update_share` | 修改已有分享（密码、过期时间、文件列表等）。 |
| `cancel_share` | `disable_share` 的别名。 |
| `delete_share` | 永久删除分享链接。需 `confirm=true`。 |
| `enable_share` | 重新启用已禁用的分享链接。 |
| `disable_share` | 临时禁用分享链接（不删除）。 |

### `admin` — 系统管理(45 个工具)

属于 `all` 档。

| 工具 | 说明 |
|------|------|
| `list_storages` | 列出所有已配置的存储后端（挂载路径、驱动、状态、空间）。 |
| `get_storage_info` | 按 ID 查看单个存储详情。 |
| `create_storage` | 用驱动名与配置 JSON 新建存储（字段见 `get_driver_info`）。需要 `confirm=true`。 |
| `update_storage` | 修改存储；先读取当前配置再合并，未指定字段保持不变。需要 `confirm=true`。 |
| `delete_storage` | 删除存储并卸载挂载。需要 `confirm=true`。 |
| `enable_storage` | 启用并重新挂载某个存储。需要 `confirm=true`。 |
| `disable_storage` | 停用某个存储（保留配置，不删除）。需要 `confirm=true`。 |
| `load_all_storages` | 重新加载并挂载所有已启用的存储。需要 `confirm=true`。 |
| `list_drivers` | 列出所有已注册的存储驱动名称。 |
| `get_driver_info` | 查看特定存储驱动的详细信息。 |
| `list_drivers_detail` | 列出所有驱动及其完整配置模板。 |
| `get_settings` | 列出所有全局设置。 |
| `get_setting` | 按 key 查询单个设置（如 `site_title`）。 |
| `save_settings` | 原子性更新一个或多个全局设置。需要 `confirm=true`。 |
| `delete_setting` | 删除自定义设置。需要 `confirm=true`。 |
| `set_aria2` | 配置 aria2 离线下载客户端（`uri`、`secret`）。需要 `confirm=true`。 |
| `set_qbittorrent` | 配置 qBittorrent 客户端（`url`、`seedtime`）。需要 `confirm=true`。 |
| `set_transmission` | 配置 Transmission 客户端（`uri`、`seedtime`）。需要 `confirm=true`。 |
| `set_115` | 配置 115 客户端（`temp_dir`）。需要 `confirm=true`。 |
| `set_115_open` | 配置 115 Open 客户端（`temp_dir`）。需要 `confirm=true`。 |
| `set_123_pan` | 配置 123 网盘客户端（`temp_dir`）。需要 `confirm=true`。 |
| `set_123_open` | 配置 123 Open 客户端（`temp_dir`、`callback_url`）。需要 `confirm=true`。 |
| `set_pikpak` | 配置 PikPak 客户端（`temp_dir`）。需要 `confirm=true`。 |
| `set_thunder` | 配置迅雷客户端（`temp_dir`）。需要 `confirm=true`。 |
| `set_thunderx` | 配置 ThunderX 客户端（`temp_dir`）。需要 `confirm=true`。 |
| `set_thunder_browser` | 配置迅雷浏览器客户端（`temp_dir`）。需要 `confirm=true`。 |
| `set_guangyapan` | 配置光雅盘客户端（`temp_dir`）。需要 `confirm=true`。 |
| `get_index_progress` | 查看搜索索引构建进度。 |
| `build_search_index` | 触发全量重建搜索索引。需要 `confirm=true`。 |
| `update_search_index` | 触发增量更新搜索索引。需要 `confirm=true`。 |
| `stop_indexing` | 停止当前索引构建进程。需要 `confirm=true`。 |
| `clear_search_index` | 清空整个搜索索引。需要 `confirm=true`。 |
| `list_users` | 分页列出所有用户账号。 |
| `get_user` | 按 ID 查看单个用户详情。 |
| `create_user` | 新建用户（guest/admin 角色会被客户端拒绝）。需要 `confirm=true`。 |
| `update_user` | 修改用户；先读后合并，角色无法通过 API 变更。需要 `confirm=true`。 |
| `list_metas` | 列出所有元数据配置。 |
| `get_meta` | 按 ID 查看元数据详情。 |
| `create_meta` | 给目录挂元数据：密码、读写用户名单、隐藏规则、说明与头部 —— 每项都有 `*_sub` 变体可延伸到子目录。需要 `confirm=true`。 |
| `update_meta` | 修改目录元数据；先读后合并，未提及的设置保持不变。传 `""` 或 `[]` 可清空某一项。需要 `confirm=true`。 |
| `delete_meta` | 删除目录的元数据记录；**目录与文件保留**。需要 `confirm=true`。 |
| `reset_api_token` | 生成新的 API Token。需要 `confirm=true`。 |
| `start_manual_scan` | 启动对某个存储挂载点的一次性手动扫描。需要 `confirm=true`。 |
| `stop_manual_scan` | 停止正在运行的手动扫描。需要 `confirm=true`。 |
| `get_manual_scan_progress` | 获取手动扫描的进度。 |

### `advanced` — 高级与种子(16 个工具)

属于 `all` 档。

| 工具 | 说明 |
|------|------|
| `get_capabilities` | 汇总服务器设置、当前用户、可用下载工具和 MCP 安全配置。 |
| `offline_download` | 从远程 URL 直接下载文件到 OpenList 服务端。支持 `http://`、`https://`、`magnet:`、`ftp://`、`sftp://` 协议。使用 aria2、Transmission 或 qBittorrent。自动拦截内网 IP（SSRF 防护）。磁力链接无 hostname，豁免 SSRF 检查。 |
| `batch_download` | 批量离线下载多个 URL。 |
| `find_duplicates` | 按名称+大小或仅大小查找重复文件。 |
| `content_preview` | 通过 Range 请求预览文本文件内容。 |
| `get_archive_extensions` | 查询服务端支持的解压格式扩展名列表。 |
| `get_archive_meta` | 获取压缩包元数据（格式、加密状态、注释、文件树），无需解压。 |
| `decompress_archive` | 服务端在线解压压缩文件（zip、rar、7z、tar.gz 等）。 |
| `list_archive_files` | 不解压查看压缩包内文件列表。 |
| `get_me` | 获取当前用户信息（用户名、角色、权限、2FA 状态）。 |
| `logout` | 登出并使当前 token 失效。 |
| `list_download_tools` | 查询服务端配置的可用下载工具。 |
| `parse_torrent` | 解析 `.torrent` 文件（base64），返回文件列表和元数据。 |
| `torrent_upload_parse` | 通过表单上传并解析 `.torrent` 文件，返回解析信息 + 可复用的 base64 数据。 |
| `generate_torrent` | 为服务端已有文件生成 `.torrent` 种子文件。 |
| `torrent_rapid_upload` | 从种子数据尝试秒传（需存储后端支持 CAS）。 |
<!-- END GENERATED: tools -->

## 安全

- **生产环境务必使用 HTTPS** — HTTP 下凭据明文传输。
  HTTP **默认被拒绝** — 设置 `OPENLIST_ALLOW_HTTP=true` 启用（仅限受信局域网）。
- **使用低权限的专用 OpenList 账户** 进行 MCP 操作，不要用 `admin` 账户。
- **限制存储暴露范围** — 不要通过 OpenList 暴露系统路径（home、Docker 配置、SSH 密钥等）。
- **设置 `OPENLIST_READONLY=true`** 可阻止所有写入/高风险操作。
- **设置 `OPENLIST_ALLOWED_PATHS`** 为逗号分隔的路径前缀，将操作限制在允许的目录内。
- **保护 MCP 配置文件**：`chmod 600 claude_desktop_config.json`（Linux/macOS）。
- **本地文件上传默认禁用** — 需显式设置 `OPENLIST_LOCAL_UPLOAD_ROOTS`。
- **SSRF 防护** — `offline_download` 会自动解析域名并通过 DNS 拦截内网 IP。
  支持的协议：`http://`、`https://`、`ftp://`、`sftp://`（受 SSRF 检查）、`magnet:`（豁免 — 无 hostname）。
- **破坏性操作**（`remove`、`delete_share`、`delete_task` 等）需要 `confirm=true` 防止误操作。

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `OPENLIST_URL is required` | 未设置环境变量 | 设置 `OPENLIST_URL`、`OPENLIST_USERNAME`、`OPENLIST_PASSWORD` |
| `password is incorrect` | 凭据错误 | 核实 OpenList 用户名和密码 |
| `Connection refused` | OpenList 未运行 | 检查 OpenList 服务状态 |
| `search not available` | 搜索索引未启用 | 在 OpenList 管理后台启用搜索 |
| `2FA code is required` | 账户开启了两步验证 | 设置 `OPENLIST_TOTP_SECRET` 或传 `otp_code` |
| `upload_local_file` 被拒 | 未设 `OPENLIST_LOCAL_UPLOAD_ROOTS` | 设置允许的目录路径 |
| 离线下载任务卡住 | aria2 未运行 | 在 OpenList 服务端启动 aria2 RPC |
| `URL points to private IP` | SSRF 防护触发 | 使用公网 URL |
| HTTP 警告 | 使用了 HTTP 协议 | 生产环境请用 HTTPS |

---

## 更新日志

完整版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT
