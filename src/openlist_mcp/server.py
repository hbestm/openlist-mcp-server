"""OpenList MCP Server - main entry point.

This server exposes OpenList file management capabilities as MCP tools,
enabling AI agents to browse, upload, download, search, and manage files
on any OpenList instance.

Usage:
    openlist-mcp

Environment Variables:
    OPENLIST_URL      - Base URL of your OpenList instance (required)
    OPENLIST_USERNAME - Username for authentication (required)
    OPENLIST_PASSWORD - Password for authentication (required)
    OPENLIST_TOTP_SECRET - TOTP secret for automatic 2FA (optional)
    OPENLIST_READONLY - When true, blocks all write/modify tools (optional)
    OPENLIST_ALLOWED_PATHS - Comma-separated path allowlist (optional)
    OPENLIST_SKILLS   - Tool groups to load: core|default|all|custom (optional)
                        core=~25tools, default=~44tools, all=79tools(default)
                        custom example: "fs,transfer,task"
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable

from mcp.server.mcpserver import MCPServer as FastMCP

from . import __version__  # noqa: F401 — used in except ValueError branch
from .config import get_config
from .skills import ALWAYS_LOADED, SKILL_GROUP_META, SKILL_PRESETS, group_count, resolve_skills
from .tools.admin import register_admin_tools
from .tools.advanced import register_advanced_tools
from .tools.auth import register_auth_tools, register_public_tools
from .tools.fs import register_fs_tools
from .tools.share import register_share_tools
from .tools.task import register_task_tools
from .tools.transfer import register_transfer_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("openlist-mcp")

# Create MCP server instance
mcp = FastMCP(
    name="openlist",
    instructions=(
        "OpenList MCP Server - Manage files on your OpenList instance. "
        "You can browse directories, search files, upload/download, "
        "create folders, rename/copy/move/delete files, manage shares, "
        "and monitor async tasks. "
        "Authentication is handled automatically on first use."
    ),
)

# Group → registration function mapping (server-only, kept here)
_REGISTER_FUNC: dict[str, Callable[[FastMCP], None]] = {
    "fs": register_fs_tools,
    "transfer": register_transfer_tools,
    "task": register_task_tools,
    "share": register_share_tools,
    "admin": register_admin_tools,
    "advanced": register_advanced_tools,
}

# Groups that always load (auth) + their count
AUTH_COUNT = group_count("auth")


def register_all_tools() -> None:
    """Register tool groups with the MCP server, filtered by OPENLIST_SKILLS."""
    config = get_config()
    selected = resolve_skills(config.skills)

    # Auth/public tools are always loaded (needed for any interaction)
    register_public_tools(mcp)
    register_auth_tools(mcp)

    loaded = list(ALWAYS_LOADED)
    for group_name in sorted(selected):
        if group_name in _REGISTER_FUNC:
            _REGISTER_FUNC[group_name](mcp)
            cnt = group_count(group_name)
            meta = SKILL_GROUP_META[group_name]
            loaded.append(f"{group_name}({cnt})")
            logger.info("  Loaded skill group: %s (%s, %d tools)", group_name, meta["desc"], cnt)

    logger.info("Skills loaded: %s", ", ".join(loaded))


def _banner_skills(raw_skills: str) -> tuple[int, list[str], str, str]:
    """Build skill summary for the missing-config banner.
    Returns (total, group_details, skills_line, upgrade_notice).
    """
    selected = resolve_skills(raw_skills)
    total = AUTH_COUNT + sum(group_count(g) for g in selected if g in SKILL_GROUP_META)
    group_details = []
    upgrade_notice = ""
    for name in sorted(SKILL_GROUP_META.keys()):
        if name == "auth":
            continue
        cnt = group_count(name)
        meta = SKILL_GROUP_META[name]
        mark = "✓" if name in selected else " "
        group_details.append(f"  [{mark}] {name:<12} {meta['desc']:<32} ({cnt}个)")
    if raw_skills in ("core",) or all(
        g not in selected for g in ("admin", "advanced", "task", "share")
    ):
        upgrade_notice = "║  Tip: Set OPENLIST_SKILLS=all to load all 79 tools.              ║\n"
    preset_label = raw_skills if raw_skills in SKILL_PRESETS else "custom"
    return total, group_details, f"{preset_label:<17} {total:>3} tools loaded", upgrade_notice


def main() -> None:
    """Main entry point for the OpenList MCP Server."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        config = get_config()
    except ValueError:
        raw_skills = os.environ.get("OPENLIST_SKILLS", "core").strip().lower()
        total, group_details, skills_line, upgrade_notice = _banner_skills(raw_skills)
        print(
            "\n"
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║              OpenList MCP Server v{__version__:<24}║\n"
            "╠══════════════════════════════════════════════════════════════╣\n"
            "║                                                              ║\n"
            "║  What is this?                                               ║\n"
            "║  An MCP server that lets AI agents (Claude, SOLO, etc.)      ║\n"
            "║  manage files on your OpenList instance.                     ║\n"
            "║                                                              ║\n"
            f"║  Skills preset: {skills_line:<38}║\n"
            "║                                                              ║\n"
            "║  Loaded groups:                                              ║\n"
            f"║  [✓] auth       认证/SSH密钥/个人设置              (6个)                 ║\n"
            + "\n".join(f"║{g:<77}║" for g in group_details)
            + "\n"
            "║                                                              ║\n"
            "║  Quick start:                                                ║\n"
            "║  Set these environment variables and restart:                ║\n"
            "║                                                              ║\n"
            "║    export OPENLIST_URL=https://your-openlist.com             ║\n"
            "║    export OPENLIST_USERNAME=your_username                     ║\n"
            "║    export OPENLIST_PASSWORD=your_password                    ║\n"
            "║                                                              ║\n"
            "║  Skill config (optional):                                    ║\n"
            "║    export OPENLIST_SKILLS=core      # ~25个基础工具          ║\n"
            "║    export OPENLIST_SKILLS=default   # ~44个日常工具          ║\n"
            "║    export OPENLIST_SKILLS=all       # 全部79个工具           ║\n"
            "║    # 或自定义组合: export OPENLIST_SKILLS=fs,transfer,task  ║\n"
            "║                                                              ║\n"
            + upgrade_notice
            + '║  Then try: "List files on my OpenList server."               ║\n'
            "║                                                              ║\n"
            "║  For more: https://github.com/hbestm/openlist-mcp-server     ║\n"
            "║                                                              ║\n"
            "╚══════════════════════════════════════════════════════════════╝\n",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info("OpenList MCP Server starting")
    logger.info("Target: %s", config.base_url)
    if config.is_authenticated:
        logger.info("Authentication: configured")
    else:
        logger.warning(
            "Authentication: not configured. "
            "Set OPENLIST_USERNAME and OPENLIST_PASSWORD for full access."
        )

    selected = resolve_skills(config.skills)
    total = AUTH_COUNT + sum(group_count(g) for g in selected if g in SKILL_GROUP_META)
    logger.info(
        "Skills: preset=%s, groups=%s, total=%d tools",
        config.skills if config.skills in SKILL_PRESETS else "custom",
        ", ".join(sorted(selected)),
        total,
    )

    register_all_tools()
    mcp.run()


if __name__ == "__main__":
    main()
