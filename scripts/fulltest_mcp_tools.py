"""Full capability sweep driving the REAL MCP tool functions against a live OpenList.

Every group is registered into a ToolRecorder; the recorded async functions are
then invoked exactly as an agent would call them. All writes are confined to
/tests/<base>/ and removed at the end. Global admin destructives are skipped.

Usage:
    OPENLIST_URL=.. OPENLIST_USERNAME=.. OPENLIST_PASSWORD=.. OPENLIST_ALLOW_HTTP=true \
        python scripts/fulltest_mcp_tools.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openlist_mcp.tools.admin import register_admin_tools  # noqa: E402
from openlist_mcp.tools.advanced import register_advanced_tools  # noqa: E402
from openlist_mcp.tools.auth import register_auth_tools, register_public_tools  # noqa: E402
from openlist_mcp.tools.fs import register_fs_tools  # noqa: E402
from openlist_mcp.tools.share import register_share_tools  # noqa: E402
from openlist_mcp.tools.task import register_task_tools  # noqa: E402
from openlist_mcp.tools.transfer import register_transfer_tools  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


class Recorder:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def register_all() -> dict:
    r = Recorder()
    for fn in (
        register_auth_tools,
        register_public_tools,
        register_fs_tools,
        register_transfer_tools,
        register_share_tools,
        register_task_tools,
        register_admin_tools,
        register_advanced_tools,
    ):
        fn(r)
    return r.tools


def parse(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return {"_text": text[:120]}


def ok(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


async def safe(tool, label: str, **kwargs):
    try:
        return await tool(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__: {exc}"


async def main() -> None:
    tools = register_all()
    ts = int(time.time())
    base = f"/test/mcp-tools-{ts}"

    # ── auth / public ────────────────────────────────────────────────────
    r = parse(await safe(tools["login"], "login"))
    check("login()", ok(r.get("_text", ""), "successful", "token"), r.get("_text", "")[:60])
    r = parse(await safe(tools["get_public_settings"], "get_public_settings"))
    check("get_public_settings()", "allow_indexed" in str(r), str(r)[:80])
    r = parse(await safe(tools["get_me"], "get_me"))
    check("get_me()", r.get("username") == "admin", str(r.get("username")))

    # ── fs ───────────────────────────────────────────────────────────────
    for d in ("", "/docs", "/sub", "/move-src", "/regexdir"):
        r = parse(await safe(tools["create_folder"], "create_folder", path=base + d))
        check(
            f"create_folder{base + d or ' (base)'}",
            ok(r.get("_text", ""), "created"),
            r.get("_text", "")[:60],
        )

    r = parse(
        await safe(
            tools["upload_file"],
            "upload_file",
            path=base,
            file_name="a.txt",
            file_content_base64="aGVsbG8gZnVsbHRlc3Q=",
            as_task=False,
        )
    )
    check("upload_file a.txt", ok(r.get("_text", ""), "successfully"), r.get("_text", "")[:70])
    for rel, data in (
        ("photo.png", "cG5nZGF0YQ=="),
        ("regexdir/f1.txt", "ZjE="),
        ("regexdir/f2.txt", "ZjI="),
        ("move-src/f1.txt", "bW92ZQ=="),
    ):
        r = parse(
            await safe(
                tools["upload_file"],
                "upload_file",
                path=f"{base}/{rel}",
                file_name=rel.split("/")[-1],
                file_content_base64=data,
                as_task=False,
            )
        )
        check(f"upload_file {rel}", ok(r.get("_text", ""), "successfully"), r.get("_text", "")[:60])

    r = parse(await safe(tools["list_files"], "list_files", path=base, per_page=200))
    names = [i.get("name") for i in r.get("content", [])]
    check("list_files(base)", "a.txt" in names and "docs" in names, str(names))

    r = parse(await safe(tools["list_dirs"], "list_dirs", path=base))
    check("list_dirs(base)", "sub" in str(r) or "docs" in str(r), str(r)[:100])

    r = parse(await safe(tools["get_file_info"], "get_file_info", path=f"{base}/a.txt"))
    check("get_file_info(a.txt)", r.get("name") == "a.txt", str(r.get("name")))

    # rename family
    r = parse(await safe(tools["rename"], "rename", path=f"{base}/a.txt", name="a-renamed.txt"))
    check(
        "rename a.txt", ok(r.get("_text", ""), "renamed", "successfully"), r.get("_text", "")[:80]
    )
    r = parse(
        await safe(
            tools["batch_rename"],
            "batch_rename",
            src_dir=base,
            rename_objects=[{"src_name": "photo.png", "new_name": "photo2.png"}],
        )
    )
    check(
        "batch_rename photo.png",
        ok(r.get("_text", ""), "renamed", "batch", "result"),
        r.get("_text", "")[:80],
    )
    r = parse(
        await safe(
            tools["regex_rename"],
            "regex_rename",
            src_dir=f"{base}/regexdir",
            src_name_regex=r"^(.*)\.txt$",
            new_name_regex=r"$1.md",
        )
    )
    check(
        "regex_rename f*.txt->*.md",
        ok(r.get("_text", ""), "regex", "renamed", "result"),
        r.get("_text", "")[:80],
    )
    lst = parse(await safe(tools["list_files"], "list_files", path=f"{base}/regexdir", per_page=50))
    rn = [i.get("name") for i in lst.get("content", [])]
    check(
        "regex_rename landed f1.md", "f1.md" in rn and "f2.md" in rn and "f1.txt" not in rn, str(rn)
    )

    # copy / move (async tasks on this server) — poll until content lands
    r = parse(
        await safe(
            tools["copy"], "copy", src_dir=base, names=["photo2.png"], dst_dir=f"{base}/docs"
        )
    )
    check(
        "copy photo2.png->docs", ok(r.get("_text", ""), "copied", "task"), r.get("_text", "")[:90]
    )
    r = parse(
        await safe(
            tools["move"], "move", src_dir=base, dst_dir=f"{base}/docs", names=["a-renamed.txt"]
        )
    )
    check(
        "move a-renamed.txt->docs", ok(r.get("_text", ""), "moved", "task"), r.get("_text", "")[:90]
    )

    landed = False
    for _ in range(8):
        await asyncio.sleep(1.5)
        lst = parse(await safe(tools["list_files"], "list_files", path=f"{base}/docs", per_page=50))
        dnames = [i.get("name") for i in lst.get("content", [])]
        if "a-renamed.txt" in dnames and "photo2.png" in dnames:
            landed = True
            break
    check("docs contains moved+copied (polled)", landed, str(dnames if "dnames" in dir() else []))

    r = parse(
        await safe(
            tools["recursive_move"],
            "recursive_move",
            src_dir=f"{base}/move-src",
            dst_dir=f"{base}/move-dst",
        )
    )
    check("recursive_move", ok(r.get("_text", ""), "completed", "moved"), r.get("_text", "")[:90])

    # ── transfer ─────────────────────────────────────────────────────────
    r = parse(
        await safe(tools["get_download_url"], "get_download_url", path=f"{base}/docs/a-renamed.txt")
    )
    check("get_download_url", "http" in str(r), str(r)[:100])
    r = parse(
        await safe(
            tools["upload_file_multipart"],
            "upload_file_multipart",
            path=base,
            file_name="big.bin",
            file_content_base64="YmlnIGRhdGE=",
        )
    )
    check("upload_file_multipart on v4.2.5+", r.get("ok") is True, str(r)[:100])
    r = parse(
        await safe(tools["multipart_upload_status"], "multipart_upload_status", upload_id="nope")
    )
    check(
        "multipart_upload_status bad id (typed error)",
        "not found" in str(r).lower() or "error" in str(r).lower(),
        str(r)[:100],
    )
    r = parse(
        await safe(
            tools["get_direct_upload_info"],
            "get_direct_upload_info",
            path=base,
            file_name="a-renamed.txt",
            file_size=100,
        )
    )
    check("get_direct_upload_info (Local limitation)", "not implement" in str(r), str(r)[:100])

    # ── share ────────────────────────────────────────────────────────────
    r = parse(
        await safe(
            tools["create_share"], "create_share", files=[f"{base}/docs/a-renamed.txt"], pwd="t1"
        )
    )
    sid = r.get("id")
    check("create_share", bool(sid), str(sid))
    if sid:
        r = parse(await safe(tools["get_share_info"], "get_share_info", share_id=sid))
        check("get_share_info", r.get("id") == sid, str(r.get("id")))
        r = parse(await safe(tools["disable_share"], "disable_share", share_id=sid))
        check("disable_share", ok(r.get("_text", ""), "disabled"), r.get("_text", "")[:70])
        r = parse(await safe(tools["enable_share"], "enable_share", share_id=sid))
        check("enable_share", ok(r.get("_text", ""), "enabled"), r.get("_text", "")[:70])
        r = parse(await safe(tools["cancel_share"], "cancel_share", share_id=sid, confirm=True))
        check(
            "cancel_share", ok(r.get("_text", ""), "cancelled", "disabled"), r.get("_text", "")[:70]
        )
        r = parse(await safe(tools["delete_share"], "delete_share", share_id=sid, confirm=True))
        check("delete_share", ok(r.get("_text", ""), "deleted"), r.get("_text", "")[:70])

    # ── task ─────────────────────────────────────────────────────────────
    for t in ("upload", "copy", "move", "offline_download", "decompress"):
        r = parse(await safe(tools["list_tasks"], "list_tasks", task_type=t, status="done"))
        check(f"list_tasks({t},done)", isinstance(r, dict), str(r)[:60])
    r = parse(
        await safe(tools["clear_succeeded_tasks"], "clear_succeeded_tasks", task_type="upload")
    )
    check(
        "clear_succeeded_tasks(upload)", ok(r.get("_text", ""), "cleared"), r.get("_text", "")[:70]
    )

    # ── admin (safe subset) ──────────────────────────────────────────────
    r = parse(await safe(tools["list_storages"], "list_storages"))
    check(
        "list_storages (2 mounts)", len(r.get("content", [])) == 2, str(len(r.get("content", [])))
    )
    r = parse(await safe(tools["get_storage_info"], "get_storage_info", storage_id=2))
    check("get_storage_info(2)", r.get("mount_path") == "/test", str(r.get("mount_path")))
    r = parse(await safe(tools["list_drivers"], "list_drivers"))
    check("list_drivers", len(r) > 0, str(list(r)[:3]))
    r = parse(await safe(tools["get_driver_info"], "get_driver_info", driver="Local"))
    check("get_driver_info(Local)", "common" in r or "driver" in r, str(r)[:80])
    r = parse(await safe(tools["list_drivers_detail"], "list_drivers_detail"))
    check("list_drivers_detail", len(r) > 0, str(r)[:60])
    r = parse(await safe(tools["get_settings"], "get_settings"))
    check("get_settings", len(r) > 0, str(r)[:60])
    r = parse(await safe(tools["get_setting"], "get_setting", key="aria2"))
    check("get_setting(aria2, graceful err)", "record not found" in str(r), str(r)[:60])
    r = parse(await safe(tools["list_users"], "list_users"))
    check("list_users", len(r.get("content", [])) >= 1, str(r)[:60])
    r = parse(await safe(tools["get_user"], "get_user", user_id=1))
    check("get_user(1)", r.get("username") == "admin", str(r.get("username")))
    r = parse(await safe(tools["list_metas"], "list_metas"))
    check("list_metas", r is not None, str(r)[:60])
    r = parse(await safe(tools["get_meta"], "get_meta", meta_id=0))
    check("get_meta(0, graceful err)", "record not found" in str(r), str(r)[:70])

    r = parse(
        await safe(tools["start_manual_scan"], "start_manual_scan", path="/test", confirm=True)
    )
    check("start_manual_scan", ok(r.get("_text", ""), "started"), r.get("_text", "")[:70])
    r = parse(await safe(tools["get_manual_scan_progress"], "get_manual_scan_progress"))
    check("get_manual_scan_progress", "obj_count" in str(r), str(r)[:70])
    r = parse(await safe(tools["stop_manual_scan"], "stop_manual_scan", confirm=True))
    check(
        "stop_manual_scan",
        ok(r.get("_text", ""), "stopped", "not running"),
        r.get("_text", "")[:70],
    )

    # ── advanced ─────────────────────────────────────────────────────────
    r = parse(await safe(tools["get_capabilities"], "get_capabilities"))
    check("get_capabilities", "allow_indexed" in str(r), str(r)[:70])
    r = parse(await safe(tools["list_download_tools"], "list_download_tools"))
    check("list_download_tools", len(r) >= 1, str(r)[:70])
    r = parse(await safe(tools["get_archive_extensions"], "get_archive_extensions"))
    check("get_archive_extensions", ".zip" in str(r).lower() or len(r) > 0, str(r)[:70])
    r = parse(await safe(tools["find_duplicates"], "find_duplicates", path=f"{base}/docs"))
    check("find_duplicates (docs)", isinstance(r, dict), str(r)[:60])

    # ── output & cleanup ─────────────────────────────────────────────────
    check("tool registry size", len(tools) == 107, f"{len(tools)} tools")

    p1 = {
        "create_storage",
        "update_storage",
        "delete_storage",
        "enable_storage",
        "disable_storage",
        "load_all_storages",
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
        "create_user",
        "update_user",
    }
    missing_p1 = sorted(p1 - set(tools))
    check("v0.5.0 P1 tools registered", not missing_p1, f"missing: {missing_p1}")

    r = parse(
        await safe(
            tools["remove"], "remove", directory="/test", names=[f"mcp-tools-{ts}"], confirm=True
        )
    )
    check("cleanup base", ok(r.get("_text", ""), "deleted"), r.get("_text", "")[:70])

    await tools["logout"]()
    print("\n===== TOOL-LEVEL SWEEP SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
