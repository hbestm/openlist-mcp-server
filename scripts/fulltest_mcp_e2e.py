"""MCP-protocol-level stability & robustness against the live OpenList.

Drives the packaged server over stdio (initialize -> tools/call) the same way
an AI agent would: repeated calls, bad inputs (must return clean tool error
text, not crash the server), and the full share lifecycle. Confined to /test.

Usage:
    OPENLIST_URL=.. OPENLIST_USERNAME=.. OPENLIST_PASSWORD=.. OPENLIST_ALLOW_HTTP=true \
        python scripts/fulltest_mcp_e2e.py
"""

import asyncio
import contextlib
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

# A disposable directory inside a writable mount. Required, not defaulted:
# these suites create and delete files, so guessing a target would risk real data.
TEST_DIR = os.environ.get("OPENLIST_TEST_DIR", "").strip().rstrip("/")
if not TEST_DIR:
    raise SystemExit(
        "OPENLIST_TEST_DIR is required: point it at a disposable directory inside a "
        "writable mount, e.g. OPENLIST_TEST_DIR=/scratch/mcp (the server root is refused)."
    )

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def text(res) -> str:
    return " ".join(c.text or "" for c in (res.content or []))


async def call(session, tool: str, args: dict | None = None):
    return await session.call_tool(tool, args or {})


def _child_env() -> dict[str, str]:
    """Build the environment for the spawned server from this process's own.

    The connection settings are forwarded, never defaulted: a missing value is a
    configuration error worth failing on, and a hard-coded host or password here
    would publish that instance's credentials to everyone who can read the repo.
    """
    required = ("OPENLIST_URL", "OPENLIST_USERNAME", "OPENLIST_PASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing required environment variable(s): {', '.join(missing)}")
    return {
        **{name: os.environ[name] for name in required},
        "OPENLIST_ALLOW_HTTP": os.environ.get("OPENLIST_ALLOW_HTTP", "true"),
        # The suite asserts the full registry, so the child must load every group.
        "OPENLIST_SKILLS": os.environ.get("OPENLIST_SKILLS", "all"),
    }


async def main() -> None:
    env = _child_env()
    server_params = StdioServerParameters(
        command=sys.executable, args=["-m", "openlist_mcp.server"], env=env
    )
    ts = int(time.time())
    base = f"{TEST_DIR}/mcp-e2e-{ts}"

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools = await session.list_tools()
        check("110 tools over stdio", len(tools.tools) == 110, f"{len(tools.tools)}")

        r = await call(session, "login")
        check("login", "successful" in text(r).lower() or "token" in text(r).lower(), text(r)[:60])

        r = await call(session, "create_folder", {"path": base})
        check("create_folder", "created" in text(r).lower(), text(r)[:60])
        r = await call(
            session,
            "upload_file",
            {
                "path": base,
                "file_name": "s.txt",
                "file_content_base64": "c3RhYmlsaXR5",
                "as_task": False,
            },
        )
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
        check(
            "bad path over protocol (error text)",
            "error" in text(r).lower() or "relative" in text(r).lower(),
            text(r)[:80],
        )
        r = await call(
            session,
            "upload_file",
            {
                "path": base,
                "file_name": "bad.txt",
                "file_content_base64": "!!!not-base64!!!",
                "as_task": False,
            },
        )
        check(
            "bad base64 over protocol (error text)",
            "error" in text(r).lower()
            or "invalid" in text(r).lower()
            or "base64" in text(r).lower(),
            text(r)[:80],
        )
        # server still alive after errors
        r = await call(session, "get_me")
        check("server alive after error calls", "admin" in text(r), text(r)[:60])

        # 3. share lifecycle via protocol
        r = await call(session, "create_share", {"files": [f"{base}/s.txt"], "pwd": "e2e"})
        sid = None
        with contextlib.suppress(Exception):
            sid = json.loads(text(r)).get("id")
        check("create_share", bool(sid), str(sid))
        if sid:
            for tool, needle in (
                ("disable_share", "disabled"),
                ("enable_share", "enabled"),
                ("get_share_info", sid),
                ("delete_share", "deleted"),
            ):
                args = {"share_id": sid} if tool != "get_share_info" else {"share_id": sid}
                if tool == "delete_share":
                    args["confirm"] = True
                r = await call(session, tool, args)
                check(
                    f"{tool} via protocol",
                    needle in text(r).lower() or needle in text(r),
                    text(r)[:60],
                )

        # 4. task listing across types via protocol
        for t in ("upload", "copy", "move"):
            r = await call(session, "list_tasks", {"task_type": t, "status": "done"})
            check(f"list_tasks({t}) via protocol", "value" in text(r), text(r)[:50])

        # 5. multipart upload via protocol (v4.2.5+)
        r = await call(
            session,
            "upload_file_multipart",
            {"path": base, "file_name": "big.bin", "file_content_base64": "Ymln", "chunk_size": 8},
        )
        check(
            "multipart upload via protocol",
            "complete" in text(r).lower() or "ok" in text(r).lower(),
            text(r)[:80],
        )

        # 6. manual scan via protocol
        r = await call(session, "start_manual_scan", {"path": TEST_DIR, "confirm": True})
        check("start_manual_scan", "started" in text(r).lower(), text(r)[:60])
        r = await call(session, "get_manual_scan_progress", {})
        check("get_manual_scan_progress", "obj_count" in text(r), text(r)[:60])
        r = await call(session, "stop_manual_scan", {"confirm": True})
        check(
            "stop_manual_scan",
            "stopped" in text(r).lower() or "not running" in text(r).lower(),
            text(r)[:60],
        )

        # 7. cleanup + logout
        r = await call(
            session, "remove", {"directory": TEST_DIR, "names": [f"mcp-e2e-{ts}"], "confirm": True}
        )
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
