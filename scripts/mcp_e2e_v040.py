"""Full MCP-protocol end-to-end test against the live OpenList instance.

Starts the packaged ``openlist-mcp`` server over stdio and drives it with a
real MCP client (initialize -> tools/call), exercising the v0.4.0 share fix
and basic file ops through the exact path an AI agent would use.

Run with:  PYTHONPATH=src python scripts/mcp_e2e_v040.py
"""

import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


async def main() -> None:
    env = {
        "OPENLIST_URL": os.environ.get("OPENLIST_URL", "http://192.168.123.199:5244"),
        "OPENLIST_USERNAME": os.environ.get("OPENLIST_USERNAME", "admin"),
        "OPENLIST_PASSWORD": os.environ.get("OPENLIST_PASSWORD", "openlist123"),
        "OPENLIST_ALLOW_HTTP": "true",
        "OPENLIST_SKILLS": "all",
    }

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "openlist_mcp.server"],
        env=env,
    )

    ts = int(time.time())
    base = f"/199/mcp-e2e-{ts}"
    hello = f"{base}/hello.txt"

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools = await session.list_tools()
        names = sorted(t.name for t in tools.tools)
        check("server starts & lists 87 tools", len(names) == 87, f"{len(names)} tools")

        login = await session.call_tool("login")
        txt = login.content[0].text if login.content else ""
        check("call_tool login", "Login successful" in txt, txt[:60])

        listing = await session.call_tool("list_files", {"path": "/199", "per_page": 10})
        txt = listing.content[0].text if listing.content else ""
        check("call_tool list_files /199", bool(txt) and "content" in txt, txt[:80])

        mk = await session.call_tool("create_folder", {"path": base})
        check("call_tool create_folder", mk.content[0].text.startswith("Folder created") if mk.content else False)

        import base64 as b64

        up = await session.call_tool(
            "upload_file",
            {"path": base, "file_name": "hello.txt", "file_content_base64": b64.b64encode(b"e2e hello").decode(), "as_task": False},
        )
        check("call_tool upload_file", "successfully" in (up.content[0].text if up.content else ""), (up.content[0].text if up.content else "")[:80])

        # ---- the v0.4.0 critical fix through the MCP protocol ----
        share = await session.call_tool("create_share", {"files": [hello], "pwd": "e2e"})
        share_txt = share.content[0].text if share.content else ""
        try:
            share_id = json.loads(share_txt).get("id")
        except Exception:
            share_id = None
        check("call_tool create_share", bool(share_id), str(share_id))

        if share_id:
            dis = await session.call_tool("disable_share", {"share_id": share_id})
            check("call_tool disable_share (v0.4.0 fix)", "disabled" in (dis.content[0].text if dis.content else ""), (dis.content[0].text if dis.content else "")[:80])
            en = await session.call_tool("enable_share", {"share_id": share_id})
            check("call_tool enable_share (v0.4.0 fix)", "enabled" in (en.content[0].text if en.content else ""), (en.content[0].text if en.content else "")[:80])
            dele = await session.call_tool("delete_share", {"share_id": share_id, "confirm": True})
            check("call_tool delete_share (v0.4.0 fix)", "deleted" in (dele.content[0].text if dele.content else ""), (dele.content[0].text if dele.content else "")[:80])

        mv_tasks = await session.call_tool("list_tasks", {"task_type": "move", "status": "undone"})
        check("call_tool list_tasks move type", bool(mv_tasks.content), (mv_tasks.content[0].text if mv_tasks.content else "")[:80])

        uploads = await session.call_tool("list_tasks", {"task_type": "upload", "status": "done"})
        check("call_tool list_tasks upload done", bool(uploads.content))

        rm = await session.call_tool("remove", {"directory": "/199", "names": [f"mcp-e2e-{ts}"], "confirm": True})
        check("call_tool remove cleanup", rm.content and "Deleted" in rm.content[0].text, (rm.content[0].text if rm.content else "")[:80])

    print("\n===== MCP E2E SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("Failed:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())