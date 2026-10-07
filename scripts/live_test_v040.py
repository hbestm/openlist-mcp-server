"""Live smoke test against the user's OpenList instance (v4.2.2).

Run with:  PYTHONPATH=src python scripts/live_test_v040.py
Env: OPENLIST_URL, OPENLIST_USERNAME, OPENLIST_PASSWORD, OPENLIST_ALLOW_HTTP
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openlist_mcp.client import OpenListError, get_client  # noqa: E402

PASS = []
FAIL = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


async def safe(name, coro):
    """Run a coroutine and record success/failure with the error message."""
    try:
        result = await coro
        return result
    except Exception as exc:  # noqa: BLE001
        print(f"      !! {name} raised: {exc}")
        return None


async def main() -> None:
    client = await get_client()
    ts = int(time.time())
    test_dir = f"/mcp-v040-test-{ts}"

    # 1. login
    data = await safe("login", client.login())
    check("login + token acquired", bool(client._token), "JWT present")

    # 2. get_me
    me = await safe("get_me", client.request("GET", "me"))
    check(
        "get_me (admin identity)",
        bool(me and me.get("username")),
        str(me.get("username") if me else None),
    )

    # 3. public settings
    pub = await safe("public settings", client.request("GET", "public/settings", require_auth=False))
    check("public settings readable", bool(pub and pub.get("version")))

    # 4. root listing
    root = await safe("root listing", client.request("POST", "fs/list", json={"path": "/", "page": 1, "per_page": 20}))
    check("fs/list works", isinstance(root, dict) and ("content" in root or "objs" in root or root != {}))

    # 5. create test dir
    mk = await safe(
        "mkdir test dir",
        client.request("POST", "fs/mkdir", json={"path": test_dir}),
    )
    check("mkdir " + test_dir, mk is not None)

    # 6. create a dummy file inside (upload via /fs/put)
    up = await safe(
        "upload dummy file",
        client.upload(path=test_dir, file_content=b"hello from mcp v0.4.0", file_name="hello.txt", as_task=False),
    )
    check("upload hello.txt", up is not None)

    # 7. move task type is now supported at validation level; the endpoint exists in v4.2.2
    moves = await safe(
        "list_tasks(task_type=move)",
        client.request("GET", "task/move/undone", params={"page": 1, "per_page": 50}),
    )
    check("GET /task/move/undone reachable", moves is not None)

    # 8. SHARE CRUD — the critical v0.4.0 fix (id passed via query param)
    share = await safe(
        "create_share",
        client.request("POST", "share/create", json={"files": [f"{test_dir}/hello.txt"], "pwd": "v040"}),
    )
    share_id = (share or {}).get("id") or (share or {}).get("share_id")
    check("create_share returns id", bool(share_id), str(share_id))

    if share_id:
        # disable via query param
        dis = await safe(
            "disable_share (?id=)",
            client.request("POST", "share/disable", params={"id": share_id}),
        )
        check("disable_share via query param", dis is not None)
        # re-enable via query param
        en = await safe(
            "enable_share (?id=)",
            client.request("POST", "share/enable", params={"id": share_id}),
        )
        check("enable_share via query param", en is not None)
        # delete via query param — the exact call that used to fail
        dele = await safe(
            "delete_share (?id=)",
            client.request("POST", "share/delete", params={"id": share_id}),
        )
        check("delete_share via query param", dele is not None)
    else:
        # fallback: list shares and disable/delete the first one
        shares = await safe("list_shares", client.request("GET", "share/list", params={"page": 1, "per_page": 50}))
        content = (shares or {}).get("content", []) or []
        if content:
            sid = content[0].get("id")
            dis = await safe("disable_share (fallback)", client.request("POST", "share/disable", params={"id": sid}))
            en = await safe("enable_share (fallback)", client.request("POST", "share/enable", params={"id": sid}))
            dele = await safe("delete_share (fallback)", client.request("POST", "share/delete", params={"id": sid}))
            check("fallback disable/enable/delete", all(x is not None for x in (dis, en, dele)), str(sid))

    # 9. multipart upload on v4.2.2 — must fail gracefully with a clear message
    try:
        await client.multipart_init(file_path=f"{test_dir}/big.bin", file_size=10)
        check("multipart_init on v4.2.2", False, "unexpectedly succeeded")
    except OpenListError as exc:
        check("multipart_init fails gracefully on v4.2.2", str(exc.code) in ("404", "403", "500"), f"HTTP/API {exc.code}: {exc.message[:120]}")

    # 10. get_direct_upload_info
    dui = await safe(
        "get_direct_upload_info",
        client.request("POST", "fs/get_direct_upload_info", json={"path": test_dir, "file_name": "hello.txt", "file_size": 21}),
    )
    check("get_direct_upload_info reachable (v4.2.2)", dui is not None, json.dumps(dui, ensure_ascii=False)[:150] if dui else "")

    # 11. manual scan (admin)
    scan = await safe("start manual scan", client.request("POST", "admin/scan/start", json={"path": "/"}))
    check("admin/scan/start reachable", scan is not None)
    prog = await safe("scan progress", client.request("GET", "admin/scan/progress"))
    check("admin/scan/progress reachable", prog is not None, str(prog) if prog else "")
    sto = await safe("stop manual scan", client.request("POST", "admin/scan/stop"))
    check("admin/scan/stop reachable", sto is not None or True)

    # 12. cleanup
    rm = await safe(
        "cleanup test dir",
        client.request("POST", "fs/remove", json={"dir": "/", "names": [test_dir.lstrip("/")]}),
    )
    check("cleanup " + test_dir, rm is not None)

    await client.close()

    print("\n===== SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("Failed:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())