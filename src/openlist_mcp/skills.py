"""共享技能组定义 — 供 server.py 和 setup_skills.py 共同使用.

维护一份定义，两处引用，避免不同步。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("openlist-mcp.skills")

# ─── 每组包含的工具清单（用于展示和统计） ──────────────────────────────────────

SKILL_GROUP_TOOLS: dict[str, list[str]] = {
    "auth": [
        "login",
        "get_public_settings",
        "list_my_ssh_keys",
        "add_ssh_key",
        "delete_ssh_key",
        "update_current_user",
    ],
    "fs": [
        "list_files",
        "list_dirs",
        "get_file_info",
        "search_files",
        "create_folder",
        "rename",
        "batch_rename",
        "regex_rename",
        "copy",
        "move",
        "remove",
        "remove_empty_dirs",
        "recursive_move",
        "tree",
        "disk_usage",
        "mirror",
    ],
    "transfer": [
        "get_download_url",
        "upload_file",
        "upload_file_multipart",
        "upload_local_file",
        "multipart_upload_local_file",
        "multipart_upload_status",
        "multipart_abort_upload",
        "get_direct_upload_info",
    ],
    "task": [
        "list_tasks",
        "get_task_info",
        "delete_task",
        "retry_task",
        "cancel_task",
        "batch_cancel_tasks",
        "batch_delete_tasks",
        "batch_retry_tasks",
        "clear_done_tasks",
        "clear_succeeded_tasks",
        "retry_failed_tasks",
    ],
    "share": [
        "create_share",
        "get_share_info",
        "list_shares",
        "update_share",
        "cancel_share",
        "delete_share",
        "enable_share",
        "disable_share",
    ],
    "admin": [
        "list_storages",
        "get_storage_info",
        "create_storage",
        "update_storage",
        "delete_storage",
        "enable_storage",
        "disable_storage",
        "load_all_storages",
        "list_drivers",
        "get_driver_info",
        "list_drivers_detail",
        "get_settings",
        "get_setting",
        "save_settings",
        "delete_setting",
        "set_aria2",
        "set_qbittorrent",
        "set_transmission",
        "set_115",
        "set_115_open",
        "set_123_pan",
        "set_123_open",
        "set_pikpak",
        "set_thunder",
        "set_thunderx",
        "set_thunder_browser",
        "set_guangyapan",
        "get_index_progress",
        "build_search_index",
        "update_search_index",
        "stop_indexing",
        "clear_search_index",
        "list_users",
        "get_user",
        "create_user",
        "update_user",
        "list_metas",
        "get_meta",
        "reset_api_token",
        "start_manual_scan",
        "stop_manual_scan",
        "get_manual_scan_progress",
    ],
    "advanced": [
        "get_capabilities",
        "offline_download",
        "batch_download",
        "find_duplicates",
        "content_preview",
        "get_archive_extensions",
        "get_archive_meta",
        "decompress_archive",
        "list_archive_files",
        "get_me",
        "logout",
        "list_download_tools",
        "parse_torrent",
        "torrent_upload_parse",
        "generate_torrent",
        "torrent_rapid_upload",
    ],
}

# ─── 组元数据（描述） — count 从 SKILL_GROUP_TOOLS 动态计算 ─────────────────

SKILL_GROUP_META: dict[str, dict[str, str]] = {
    "auth": {"desc": "认证/SSH密钥/个人设置"},
    "fs": {"desc": "文件浏览/搜索/创建/重命名/复制/移动/删除"},
    "transfer": {"desc": "上传/下载/获取下载链接"},
    "task": {"desc": "异步任务管理(列表/重试/取消/清理)"},
    "share": {"desc": "分享链接管理(创建/查询/取消/删除)"},
    "admin": {"desc": "存储/驱动/系统设置/索引/用户/元数据管理"},
    "advanced": {"desc": "离线下载/压缩包管理/种子/查重/预览"},
}

# ─── 预设定义 ────────────────────────────────────────────────────────────

SKILL_PRESETS: dict[str, set[str]] = {
    "core": {"fs", "transfer"},
    "default": {"fs", "transfer", "task", "share"},
    "all": {"fs", "transfer", "task", "share", "admin", "advanced"},
}

# ─── 工具函数 ────────────────────────────────────────────────────────────

ALWAYS_LOADED = {"auth"}


def group_count(name: str) -> int:
    """返回指定工具组的工具数."""
    return len(SKILL_GROUP_TOOLS.get(name, []))


def resolve_skills(raw: str) -> set[str]:
    """将 OPENLIST_SKILLS 值解析为组名集合."""
    raw = raw.strip().lower()
    if raw in SKILL_PRESETS:
        return set(SKILL_PRESETS[raw])

    requested = {g.strip() for g in raw.split(",") if g.strip()}
    valid = {g for g in requested if g in SKILL_GROUP_META}
    invalid = requested - valid
    if invalid:
        logger.warning(
            "Ignored invalid skill group names: %s. Valid: %s",
            ", ".join(sorted(invalid)),
            ", ".join(sorted(SKILL_GROUP_META.keys())),
        )
    return valid


def count_tools(groups: set[str]) -> int:
    """计算选中组（含 auth）的工具总数."""
    total = group_count("auth")
    for g in groups:
        if g in SKILL_GROUP_META and g != "auth":
            total += group_count(g)
    return total
