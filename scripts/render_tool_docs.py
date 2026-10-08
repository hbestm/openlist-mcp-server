#!/usr/bin/env python3
"""Render the generated tool-reference blocks in the READMEs and AI_GUIDE.

A tool is declared exactly once, in its own module. `SKILL_GROUP_TOOLS` says which
group it belongs to and the tool's docstring — the text the model itself reads —
supplies its description. This script projects those two facts into the
documentation, so a tool cannot be added in one place and forgotten in another.

    README.md      <!-- BEGIN GENERATED: tools -->        ... <!-- END GENERATED: tools -->
    README-zh.md   <!-- BEGIN GENERATED: tools -->        ... <!-- END GENERATED: tools -->
    AI_GUIDE.md    <!-- BEGIN GENERATED: tool-groups --> ... <!-- END GENERATED: tool-groups -->

Chinese descriptions cannot be derived from code, so they live in `_ZH` below. A
tool with no entry there is a hard error rather than a silent English fallback:
adding a tool without translating it must fail the check, not ship a table that is
half translated.

Usage:
    python scripts/render_tool_docs.py            # rewrite the blocks in place
    python scripts/render_tool_docs.py --check    # exit 1 when a block is stale
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openlist_mcp.skills import (  # noqa: E402
    ALWAYS_LOADED,
    SKILL_GROUP_TOOLS,
    SKILL_PRESETS,
)

# Reading order, which is also the tier order: what `core` gives you, then what
# `default` adds, then what only `all` has. A reader can see where each tier ends.
GROUP_ORDER = ("auth", "fs", "transfer", "task", "share", "admin", "advanced")

GROUP_LABEL_ZH = {
    "auth": "认证",
    "fs": "文件系统",
    "transfer": "传输",
    "task": "任务",
    "share": "分享",
    "admin": "系统管理",
    "advanced": "高级与种子",
}

# The modules that register tools, and the functions to call on each.
_REGISTRARS = (
    ("openlist_mcp.tools.auth", ("register_auth_tools", "register_public_tools")),
    ("openlist_mcp.tools.fs", ("register_fs_tools",)),
    ("openlist_mcp.tools.transfer", ("register_transfer_tools",)),
    ("openlist_mcp.tools.share", ("register_share_tools",)),
    ("openlist_mcp.tools.task", ("register_task_tools",)),
    ("openlist_mcp.tools.admin", ("register_admin_tools",)),
    ("openlist_mcp.tools.advanced", ("register_advanced_tools",)),
)

_TIERS = ("core", "default", "all")


class _Recorder:
    """Stands in for the MCP server: keeps the functions each registrar defines."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def load_descriptions() -> dict[str, str]:
    """First paragraph of each tool's docstring — the text the model reads."""
    recorder = _Recorder()
    for module_name, function_names in _REGISTRARS:
        module = importlib.import_module(module_name)
        for function_name in function_names:
            getattr(module, function_name)(recorder)
    descriptions = {}
    for name, fn in recorder.tools.items():
        doc = (getattr(fn, "__doc__", "") or "").strip()
        first = doc.split("\n\n", 1)[0].replace("\n", " ")
        descriptions[name] = re.sub(r"\s+", " ", first).strip()
    return descriptions


def tiers_for(group: str) -> list[str]:
    """Which tiers carry this group. `auth` is always loaded, so it is in all of them."""
    if group in ALWAYS_LOADED:
        return list(_TIERS)
    return [tier for tier in _TIERS if group in SKILL_PRESETS[tier]]


def _cell(text: str) -> str:
    """A description can hold a pipe; a table cell cannot."""
    return text.replace("|", "\\|")


def _verify_complete(descriptions: dict[str, str]) -> None:
    declared = {t for tools in SKILL_GROUP_TOOLS.values() for t in tools}
    unknown = sorted(set(descriptions) - declared)
    undocumented = sorted(declared - set(descriptions))
    untranslated = sorted(declared - set(_ZH))
    if unknown:
        raise SystemExit(f"registered but not in SKILL_GROUP_TOOLS: {unknown}")
    if undocumented:
        raise SystemExit(f"declared in SKILL_GROUP_TOOLS but not registered: {undocumented}")
    if untranslated:
        raise SystemExit(f"missing a Chinese description in _ZH: {untranslated}")


def render_tools(descriptions: dict[str, str], *, zh: bool) -> str:
    """The per-group tool tables used by both READMEs."""
    blocks = []
    for group in GROUP_ORDER:
        names = SKILL_GROUP_TOOLS[group]
        tiers = ", ".join(f"`{t}`" for t in tiers_for(group))
        if zh:
            label = GROUP_LABEL_ZH[group]
            blocks.append(f"### `{group}` — {label}({len(names)} 个工具)")
            blocks.append("")
            blocks.append(f"属于 {tiers} 档。")
            blocks.append("")
            blocks.append("| 工具 | 说明 |")
            blocks.append("|------|------|")
            for name in names:
                blocks.append(f"| `{name}` | {_cell(_ZH[name])} |")
        else:
            blocks.append(f"### `{group}` — {len(names)} tools")
            blocks.append("")
            blocks.append(f"In tiers: {tiers}.")
            blocks.append("")
            blocks.append("| Tool | Description |")
            blocks.append("|------|-------------|")
            for name in names:
                blocks.append(f"| `{name}` | {_cell(descriptions[name])} |")
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def render_tool_groups() -> str:
    """The compact group listing AI_GUIDE hands to another assistant."""
    total = sum(len(SKILL_GROUP_TOOLS[g]) for g in GROUP_ORDER)
    lines = [
        f"**{total} tools** in {len(GROUP_ORDER)} groups — the same grouping "
        "`OPENLIST_SKILLS` selects from:",
        "",
    ]
    for group in GROUP_ORDER:
        names = SKILL_GROUP_TOOLS[group]
        lines.append(f"- `{group}` ({len(names)}): " + ", ".join(f"`{n}`" for n in names))
    return "\n".join(lines) + "\n"


# The version history table is a summary, so its cell is the first line of the
# version's first changelog bullet, cut at the first sentence.
_HIGHLIGHT_LIMIT = 110

_SECTION = re.compile(
    r"^## \[([0-9][^\]]*)\]\s*—\s*(\d{4}-\d{2}-\d{2})\n(.*?)(?=^## \[|\Z)",
    re.M | re.S,
)


def _first_highlight(body: str) -> str:
    """One line summarising a version, taken from the section it belongs to."""
    bullet = next((line.strip() for line in body.splitlines() if line.strip().startswith("- ")), "")
    text = re.sub(r"[`*]", "", bullet[2:].strip()) if bullet else ""
    if not text:
        text = next(
            (
                line.strip()
                for line in body.splitlines()
                if line.strip() and not line.startswith("#")
            ),
            "(no summary)",
        )
    text = re.sub(r"\s+", " ", text)
    first = re.split(r"(?<=[.。])\s", text)[0].rstrip(".")
    return first if len(first) <= _HIGHLIGHT_LIMIT else first[: _HIGHLIGHT_LIMIT - 3].rstrip() + "…"


def render_changelog_table() -> str:
    """The version history table, derived from the sections above it.

    Kept generated because it used to be maintained by hand at the bottom of a
    500-line file, and fell five versions behind before anyone noticed.
    """
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    entries = _SECTION.findall(text)
    lines = ["| Version | Date | Highlights |", "|---------|------|------------|"]
    lines += [
        f"| {version} | {date} | {_first_highlight(body)} |" for version, date, body in entries
    ]
    return "\n".join(lines) + "\n"


# file -> (marker name, renderer)
BLOCKS = {
    "README.md": ("tools", lambda d: render_tools(d, zh=False)),
    "README-zh.md": ("tools", lambda d: render_tools(d, zh=True)),
    "AI_GUIDE.md": ("tool-groups", lambda d: render_tool_groups()),
    "CHANGELOG.md": ("changelog-table", lambda d: render_changelog_table()),
}

_ZH: dict[str, str] = {
    "add_ssh_key": "添加新的 SSH 公钥。受 `OPENLIST_READONLY` 保护。",
    "batch_cancel_tasks": "按 ID 批量取消任务。需 `confirm=true`。",
    "batch_delete_tasks": "按 ID 批量删除任务记录。需 `confirm=true`。",
    "batch_download": "批量离线下载多个 URL。",
    "batch_rename": "批量重命名同一目录下的多个文件/文件夹。",
    "batch_retry_tasks": "按 ID 批量重试失败任务。",
    "build_search_index": "触发全量重建搜索索引。需要 `confirm=true`。",
    "cancel_share": "`disable_share` 的别名。",
    "cancel_task": "取消正在运行的任务。需 `confirm=true`。",
    "clear_done_tasks": "清除所有已完成/失败/取消的任务。",
    "clear_search_index": "清空整个搜索索引。需要 `confirm=true`。",
    "clear_succeeded_tasks": "仅清除成功完成的任务。",
    "content_preview": "通过 Range 请求预览文本文件内容。",
    "copy": "复制文件/文件夹到另一目录。",
    "create_folder": "创建目录。",
    "create_meta": "给目录挂元数据：密码、读写用户名单、隐藏规则、说明与头部 —— 每项都有 `*_sub` 变体可延伸到子目录。需要 `confirm=true`。",
    "create_share": "创建分享链接，传 `files: list[str]`（支持多文件）。",
    "create_storage": "用驱动名与配置 JSON 新建存储（字段见 `get_driver_info`）。需要 `confirm=true`。",
    "create_user": "新建用户（guest/admin 角色会被客户端拒绝）。需要 `confirm=true`。",
    "decompress_archive": "服务端在线解压压缩文件（zip、rar、7z、tar.gz 等）。",
    "delete_meta": "删除目录的元数据记录；**目录与文件保留**。需要 `confirm=true`。",
    "delete_setting": "删除自定义设置。需要 `confirm=true`。",
    "delete_share": "永久删除分享链接。需 `confirm=true`。",
    "delete_ssh_key": "按 ID 删除 SSH 公钥。需要 `confirm=true`。",
    "delete_storage": "删除存储并卸载挂载。需要 `confirm=true`。",
    "delete_task": "删除任务记录。需 `confirm=true`。",
    "disable_share": "临时禁用分享链接（不删除）。",
    "disable_storage": "停用某个存储（保留配置，不删除）。需要 `confirm=true`。",
    "disk_usage": "按目录和文件类型统计磁盘用量。",
    "enable_share": "重新启用已禁用的分享链接。",
    "enable_storage": "启用并重新挂载某个存储。需要 `confirm=true`。",
    "find_duplicates": "按名称+大小或仅大小查找重复文件。",
    "generate_torrent": "为服务端已有文件生成 `.torrent` 种子文件。",
    "get_archive_extensions": "查询服务端支持的解压格式扩展名列表。",
    "get_archive_meta": "获取压缩包元数据（格式、加密状态、注释、文件树），无需解压。",
    "get_capabilities": "汇总服务器设置、当前用户、可用下载工具和 MCP 安全配置。",
    "get_direct_upload_info": "获取支持直传的后端（S3 等）的客户端直传凭据。",
    "get_download_url": "获取文件下载直链或代理链接。",
    "get_driver_info": "查看特定存储驱动的详细信息。",
    "get_file_info": "获取文件或文件夹详情（大小、类型、存储提供商、直链）。",
    "get_index_progress": "查看搜索索引构建进度。",
    "get_manual_scan_progress": "获取手动扫描的进度。",
    "get_me": "获取当前用户信息（用户名、角色、权限、2FA 状态）。",
    "get_meta": "按 ID 查看元数据详情。",
    "get_public_settings": "获取 OpenList 公共设置（无需认证）。",
    "get_setting": "按 key 查询单个设置（如 `site_title`）。",
    "get_settings": "列出所有全局设置。",
    "get_share_info": "按 ID 查看单个分享详情。",
    "get_storage_info": "按 ID 查看单个存储详情。",
    "get_task_info": "按 ID 查询单个任务。",
    "get_user": "按 ID 查看单个用户详情。",
    "list_archive_files": "不解压查看压缩包内文件列表。",
    "list_dirs": "列出子目录（适合用作目标路径选择）。",
    "list_download_tools": "查询服务端配置的可用下载工具。",
    "list_drivers": "列出所有已注册的存储驱动名称。",
    "list_drivers_detail": "列出所有驱动及其完整配置模板。",
    "list_files": "列出目录中的文件和文件夹（支持分页）。",
    "list_metas": "列出所有元数据配置。",
    "list_my_ssh_keys": "列出当前用户的 SSH 公钥。",
    "list_shares": "列出所有分享链接。",
    "list_storages": "列出所有已配置的存储后端（挂载路径、驱动、状态、空间）。",
    "list_tasks": "按类型和状态列出异步任务。",
    "list_users": "分页列出所有用户账号。",
    "load_all_storages": "重新加载并挂载所有已启用的存储。需要 `confirm=true`。",
    "login": "使用配置的凭据登录。如果设置 `OPENLIST_TOTP_SECRET`，TOTP 自动生成；否则需传 `otp_code`。",
    "logout": "登出并使当前 token 失效。",
    "mirror": "递归目录同步 — 比较源/目标目录，复制缺失文件，可选删除多余文件。模式：`push`（src→dst）、`pull`（dst→src）、`mirror`（push + 删除 dst 中多余文件）。",
    "move": "移动文件/文件夹到另一目录。",
    "multipart_abort_upload": "中止 multipart 上传会话并丢弃分块。需 `confirm=true`。",
    "multipart_upload_local_file": "通过可续传的 multipart API 流式上传本地文件，不占用内存。",
    "multipart_upload_status": "查询 multipart 上传会话进度（按 upload_id 或 path+size）。",
    "offline_download": "从远程 URL 直接下载文件到 OpenList 服务端。支持 `http://`、`https://`、`magnet:`、`ftp://`、`sftp://` 协议。使用 aria2、Transmission 或 qBittorrent。自动拦截内网 IP（SSRF 防护）。磁力链接无 hostname，豁免 SSRF 检查。",
    "parse_torrent": "解析 `.torrent` 文件（base64），返回文件列表和元数据。",
    "recursive_move": "递归移动整个目录树（兼容 OpenList v4.2.x fallback）。",
    "regex_rename": "用 Go 风格正则批量重命名（`$1`、`$2` 引用捕获组）。",
    "remove": "删除文件/文件夹。需 `confirm=true`。",
    "remove_empty_dirs": "递归删除空目录（清理后收尾）。",
    "rename": "重命名文件或文件夹。",
    "reset_api_token": "生成新的 API Token。需要 `confirm=true`。",
    "retry_failed_tasks": "一键重试所有失败任务。",
    "retry_task": "重试失败的任务。",
    "save_settings": "原子性更新一个或多个全局设置。需要 `confirm=true`。",
    "search_files": "按关键字搜索文件（需 OpenList 启用搜索索引）。",
    "set_115": "配置 115 客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_115_open": "配置 115 Open 客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_123_open": "配置 123 Open 客户端（`temp_dir`、`callback_url`）。需要 `confirm=true`。",
    "set_123_pan": "配置 123 网盘客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_aria2": "配置 aria2 离线下载客户端（`uri`、`secret`）。需要 `confirm=true`。",
    "set_guangyapan": "配置光雅盘客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_pikpak": "配置 PikPak 客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_qbittorrent": "配置 qBittorrent 客户端（`url`、`seedtime`）。需要 `confirm=true`。",
    "set_thunder": "配置迅雷客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_thunder_browser": "配置迅雷浏览器客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_thunderx": "配置 ThunderX 客户端（`temp_dir`）。需要 `confirm=true`。",
    "set_transmission": "配置 Transmission 客户端（`uri`、`seedtime`）。需要 `confirm=true`。",
    "start_manual_scan": "启动对某个存储挂载点的一次性手动扫描。需要 `confirm=true`。",
    "stop_indexing": "停止当前索引构建进程。需要 `confirm=true`。",
    "stop_manual_scan": "停止正在运行的手动扫描。需要 `confirm=true`。",
    "torrent_rapid_upload": "从种子数据尝试秒传（需存储后端支持 CAS）。",
    "torrent_upload_parse": "通过表单上传并解析 `.torrent` 文件，返回解析信息 + 可复用的 base64 数据。",
    "tree": "递归生成目录树（带 📁/📄 图标）。",
    "update_current_user": "修改当前用户密码或基础路径。",
    "update_meta": '修改目录元数据；先读后合并，未提及的设置保持不变。传 `""` 或 `[]` 可清空某一项。需要 `confirm=true`。',
    "update_search_index": "触发增量更新搜索索引。需要 `confirm=true`。",
    "update_share": "修改已有分享（密码、过期时间、文件列表等）。",
    "update_storage": "修改存储；先读取当前配置再合并，未指定字段保持不变。需要 `confirm=true`。",
    "update_user": "修改用户；先读后合并，角色无法通过 API 变更。需要 `confirm=true`。",
    "upload_file": "通过 base64 上传文件内容（最大 100MB）。",
    "upload_file_multipart": "通过可续传的 multipart 分块 API 上传 base64 内容（支持大文件、断点续传）。需 OpenList v4.2.5+ 且开启 `multipart_enabled` 设置。",
    "upload_local_file": "上传 MCP 服务器可读取的本地文件。默认禁用，需设 `OPENLIST_LOCAL_UPLOAD_ROOTS`。",
}


def block_pattern(marker: str) -> re.Pattern[str]:
    """The marker pair that delimits one generated block in a file."""
    return re.compile(
        rf"<!-- BEGIN GENERATED: {re.escape(marker)} -->\n.*?"
        rf"<!-- END GENERATED: {re.escape(marker)} -->",
        re.S,
    )


def render_block(marker: str, body: str) -> str:
    """Wrap generated body text in its markers."""
    return f"<!-- BEGIN GENERATED: {marker} -->\n{body.rstrip()}\n<!-- END GENERATED: {marker} -->"


def expected_blocks(descriptions: dict[str, str]) -> dict[str, str]:
    """filename -> the exact block text that file should contain.

    The single description of "what the docs should say": `main` writes these,
    and the consistency test compares them against what is committed.
    """
    return {
        filename: render_block(marker, renderer(descriptions))
        for filename, (marker, renderer) in BLOCKS.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report stale blocks; do not write")
    args = parser.parse_args()

    descriptions = load_descriptions()
    _verify_complete(descriptions)

    stale = []
    for filename, wanted in expected_blocks(descriptions).items():
        marker = BLOCKS[filename][0]
        path = ROOT / filename
        text = path.read_text(encoding="utf-8")
        match = block_pattern(marker).search(text)
        if match is None:
            stale.append(f"{filename}: no '<!-- BEGIN GENERATED: {marker} -->' block")
            continue
        if match.group(0) == wanted:
            continue
        stale.append(filename)
        if not args.check:
            path.write_text(text[: match.start()] + wanted + text[match.end() :], encoding="utf-8")

    if args.check and stale:
        print("Generated blocks are out of date:")
        for item in stale:
            print(f"  - {item}")
        print("Run: python scripts/render_tool_docs.py")
        return 1

    print("Updated: " + ", ".join(stale) if stale else "Generated blocks are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
