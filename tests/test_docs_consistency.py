"""Guards that keep the documentation honest about the code.

Each fact checked here lives in two places: the code (the tool registry, the
package version, the release history) and prose that describes it. Every one of
these tests fails on the commit that lets the two disagree, so drift surfaces
immediately instead of months later when someone happens to read the file.

The generated tool tables are the exception that proves the rule: they are not
prose at all, but a projection of the registry, and `scripts/render_tool_docs.py`
writes them.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files that state counts as claims about the registry rather than as history.
COUNT_SOURCES = (
    "README.md",
    "README-zh.md",
    "AI_GUIDE.md",
    ".env.example",
    "skills/openlist-mcp-setup/SKILL.md",
)

GROUP_NAMES = ("auth", "fs", "transfer", "task", "share", "admin", "advanced")
TIER_NAMES = ("core", "default", "all")

# "admin(42)" in the env example, "`admin` 45" and "| `core` | 30 |" in prose.
_PAREN_COUNT = re.compile(rf"\b({'|'.join(GROUP_NAMES + TIER_NAMES)})\((\d{{1,3}})\)")
_BACKTICK_COUNT = re.compile(rf"`({'|'.join(GROUP_NAMES + TIER_NAMES)})`\s*[|—·]?\s*(\d{{1,3}})\b")


def _renderer():
    """Load scripts/render_tool_docs.py — not a package, so by path."""
    spec = importlib.util.spec_from_file_location(
        "render_tool_docs", ROOT / "scripts" / "render_tool_docs.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _all_tool_names() -> set[str]:
    from openlist_mcp.skills import SKILL_GROUP_TOOLS

    return {tool for tools in SKILL_GROUP_TOOLS.values() for tool in tools}


def _expected_counts() -> dict[str, int]:
    from openlist_mcp.skills import ALWAYS_LOADED, SKILL_PRESETS, count_tools, group_count

    counts = {group: group_count(group) for group in GROUP_NAMES}
    counts.update(
        {tier: count_tools(set(groups) | ALWAYS_LOADED) for tier, groups in SKILL_PRESETS.items()}
    )
    return counts


def _read(filename: str) -> str:
    return (ROOT / filename).read_text(encoding="utf-8")


# ─────────────────────── generated blocks ────────────────────────


def test_generated_blocks_are_current() -> None:
    renderer = _renderer()
    blocks = renderer.expected_blocks(renderer.load_descriptions())

    stale = [name for name, block in blocks.items() if block not in _read(name)]

    assert not stale, (
        "These files disagree with the tool registry — run "
        "`python scripts/render_tool_docs.py`:\n  " + "\n  ".join(stale)
    )


def test_every_tool_is_named_in_each_document() -> None:
    """Holds even if someone deletes the generated blocks: the names must be there."""
    names = _all_tool_names()

    for filename in ("README.md", "README-zh.md", "AI_GUIDE.md"):
        text = _read(filename)
        missing = sorted(name for name in names if f"`{name}`" not in text)
        assert not missing, f"{filename} never mentions: {missing}"


# ─────────────────────── stated counts ───────────────────────────


def test_stated_counts_match_the_registry() -> None:
    """A group or tier size quoted in prose has to equal the real one."""
    expected = _expected_counts()
    wrong: list[str] = []

    for filename in COUNT_SOURCES:
        text = _read(filename)
        for match in (*_PAREN_COUNT.finditer(text), *_BACKTICK_COUNT.finditer(text)):
            name, quoted = match.group(1), int(match.group(2))
            if name in expected and expected[name] != quoted:
                wrong.append(
                    f"{filename}: says {name}({quoted}), the registry has {expected[name]}"
                )

    assert not wrong, "Stale counts:\n  " + "\n  ".join(wrong)


# ─────────────────────── version history ─────────────────────────


def test_version_history_table_covers_every_section() -> None:
    """Independent of the generator: every version listed once, in the same order."""
    text = _read("CHANGELOG.md")
    sections = re.findall(r"^## \[([0-9][^\]]*)\]", text, re.M)
    rows = re.findall(r"^\|\s*([0-9][0-9.]*)\s*\|", text.split("## Version history", 1)[1], re.M)

    missing = [v for v in sections if v not in rows]
    extra = [v for v in rows if v not in sections]
    assert not missing and not extra, f"missing from the table: {missing}; not in the file: {extra}"
    assert rows == sections, "the table is not in the same order as the sections"


def test_the_package_version_has_a_changelog_entry() -> None:
    version = re.search(r'^version = "([^"]+)"', _read("pyproject.toml"), re.M)
    assert version, "pyproject.toml has no version"
    assert f"## [{version.group(1)}]" in _read("CHANGELOG.md"), (
        f"pyproject.toml says {version.group(1)} but CHANGELOG.md has no such entry"
    )


def test_changelog_dates_run_newest_first() -> None:
    """Catches a mistyped year, which is how 0.1.0–0.2.7 once read as 2025."""
    dates = [
        date
        for _, date in re.findall(
            r"^## \[([0-9][^\]]*)\]\s*—\s*(\d{4}-\d{2}-\d{2})", _read("CHANGELOG.md"), re.M
        )
    ]
    assert dates == sorted(dates, reverse=True), (
        "CHANGELOG dates are not in descending order: "
        + ", ".join(f"{a}>{b}" for a, b in zip(dates, dates[1:], strict=False) if a < b)
    )


# ─────────────────────── release tooling ─────────────────────────


def test_release_script_points_at_this_repository() -> None:
    """`scripts/release.py` names the GitHub repository; keep that name honest."""
    spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
    assert spec and spec.loader
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)

    declared = re.search(
        r'^Repository = "https://github\.com/([^"]+)"', _read("pyproject.toml"), re.M
    )
    assert declared, "pyproject.toml has no Repository URL"
    assert declared.group(1) == release.REPO, (
        f"release.py targets {release.REPO}, the project declares {declared.group(1)}"
    )
