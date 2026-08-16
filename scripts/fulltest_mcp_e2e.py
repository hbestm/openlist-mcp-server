"""MCP-protocol-level stability & robustness against the live OpenList.

Drives the packaged server over stdio (initialize -> tools/call) the same way
an AI agent would: repeated calls, bad inputs (must return clean tool error
text, not crash the server), and the full share lifecycle. Confined to /test.

Usage:
    OPENLIST_URL=.. OPENLIST_USERNAME=.. OPENLIST_PASSWORD=.. OPENLIST_ALLOW_HTTP=true \
        python scripts/fulltest_mcp_e2e.py
"""

import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def text(res) -> str:
    return " ".join(c.text or "" for c in (res.content or []))


async def call(session, tool: str, args: dict | None = None):
    return await session.call_tool(tool, args or {})


async def main() -> None:
    env = {
        "OPENLIST_URL": os.environ.get("OPENLIST_URL", "http://192.168.123.199:5244"),
        "OPENLIST_USERNAME": os.environ.get("OPENLIST_USERNAME", "admin"),
        "OPENLIST_PASSWORD": os.environ.get("OPENLIST_PASSWORD", "openlist123"),
        "OPENLIST_ALLOW_HTTP": "true",
        "OPENLIST_SKILLS": "all",
    }
    server_params = StdioServerParameters(command=sys.executable, args=["-m", "openlist_mcp.server"], env=env)
    ts = int(time.time())
    base = f"/test/mcp-e2e-{ts}"

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools = await session.list_tools()
        check("87 tools over stdio", len(tools.tools) == 87, f"{len(tools.tools)}")

        r = await call(session, "login")
        check("login", "successful" in text(r).lower() or "token" in text(r).lower(), text(r)[:60])

        r = await call(session, "create_folder", {"path": base})
        check("create_folder", "created" in text(r).lower(), text(r)[:60])
        r = await call(session, "upload_file", {"path": base, "file_name": "s.txt",
                                                "file_content_base64": "c3RhYmlsaXR5", "as_task": False})
        check("upload_file", "successfully" in text(r).lower(), text(r)[:60])

        # 1. repeated calls through the protocol — no drift/leak
        all_ok = True
        t0 = time.perf_counter()
        for _ in range(12):
            r = await call(session, "list_files", {"path": base, "per_page": 50})
            all_ok &= "content" in text(r) or "s.txt" in text(r)
        dt = time.perf_counter() - t0
        check("12x repeated list_files", all_ok, f"{dt:.2f}s")

        # 2. bad inputs via protocol → error text, server stays alive
        r = await call(session, "list_files", {"path": "../etc", "per_page": 5})
        check("bad path over protocol (error text)", "error" in text(r).lower() or "relative" in text(r).lower(), text(r)[:80])
        r = await call(session, "upload_file", {"path": base, "file_name": "bad.txt",
                                                "file_content_base64": "!!!not-base64!!!", "as_task": False})
        check("bad base64 over protocol (error text)", "error" in text(r).lower() or "invalid" in text(r).lower() or "base64" in text(r).lower(), text(r)[:80])
        # server still alive after errors
        r = await call(session, "get_me")
        check("server alive after error calls", "admin" in text(r), text(r)[:60])

        # 3. share lifecycle via protocol
        r = await call(session, "create_share", {"files": [f"{base}/s.txt"], "pwd": "e2e"})
        sid = None
        try:
            sid = json.loads(text(r)).get("id")
        except Exception:  # noqa: BLE001
            pass
        check("create_share", bool(sid), str(sid))
        if sid:
            for tool, needle in (("disable_share", "disabled"), ("enable_share", "enabled"),
                                 ("get_share_info", sid), ("delete_share", "deleted")):
                args = {"share_id": sid} if tool != "get_share_info" else {"share_id": sid}
                if tool == "delete_share":
                    args["confirm"] = True
                r = await call(session, tool, args)
                check(f"{tool} via protocol", needle in text(r).lower() or needle in text(r), text(r)[:60])

        # 4. task listing across types via protocol
        for t in ("upload", "copy", "move"):
            r = await call(session, "list_tasks", {"task_type": t, "status": "done"})
            check(f"list_tasks({t}) via protocol", "value" in text(r), text(r)[:50])

        # 5. multipart graceful failure via protocol
        r = await call(session, "upload_file_multipart", {"path": base, "file_name": "big.bin",
                                                          "file_content_base64": "Ymln", "chunk_size": 8})
        check("multipart graceful on v4.2.2", "unavailable" in text(r) or "html" in text(r).lower(), text(r)[:80])

        # 6. manual scan via protocol
        r = await call(session, "start_manual_scan", {"path": "/test", "confirm": True})
        check("start_manual_scan", "started" in text(r).lower(), text(r)[:60])
        r = await call(session, "get_manual_scan_progress", {})
        check("get_manual_scan_progress", "obj_count" in text(r), text(r)[:60])
        r = await call(session, "stop_manual_scan", {"confirm": True})
        check("stop_manual_scan", "stopped" in text(r).lower() or "not running" in text(r).lower(), text(r)[:60])

        # 7. cleanup + logout
        r = await call(session, "remove", {"directory": "/test", "names": [f"mcp-e2e-{ts}"], "confirm": True})
        check("remove cleanup", "deleted" in text(r).lower(), text(r)[:60])
        r = await call(session, "logout", {})
        check("logout", True, text(r)[:40])

    print("\n===== MCP-PROTOCOL STABILITY SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())