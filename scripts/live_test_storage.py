"""Live storage tests on the user's OpenList instance under an existing mount."""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openlist_mcp.client import OpenListError, get_client  # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


async def safe(name, coro):
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        print(f"      !! {name} raised: {exc}")
        return None


async def main() -> None:
    client = await get_client()
    ts = int(time.time())
    base = f"/199/mcp-live-{ts}"
    hello = f"{base}/hello.txt"

    mk = await safe("mkdir", client.request("POST", "fs/mkdir", json={"path": base}))
    check(f"mkdir {base}", mk is not None)

    up = await safe(
        "upload hello.txt",
        client.upload(path=base, file_content=b"hello from openlist-mcp v0.4.0", file_name="hello.txt", as_task=False),
    )
    check("upload hello.txt", up is not None)

    info = await safe("fs/get", client.request("POST", "fs/get", json={"path": hello}))
    check("fs/get hello.txt", bool(info and info.get("name")), (info or {}).get("name", ""))
    raw_url = (info or {}).get("raw_url", "")
    check("raw_url present", bool(raw_url), (raw_url or "")[:80])

    tree = await safe("list within dir", client.request("POST", "fs/list", json={"path": base, "page": 1, "per_page": 50}))
    check("fs/list of test dir", bool(tree and tree.get("content")))

    dui = await safe(
        "get_direct_upload_info",
        client.request("POST", "fs/get_direct_upload_info", json={"path": base, "file_name": "hello.txt", "file_size": 28}),
    )
    check("get_direct_upload_info on Local", dui is not None, json.dumps(dui, ensure_ascii=False)[:200] if dui else "")

    # share CRUD on the real file inside the mount
    share = await safe(
        "create_share",
        client.request("POST", "share/create", json={"files": [hello], "pwd": "v040x"}),
    )
    share_id = (share or {}).get("id")
    check("create_share returns id", bool(share_id), str(share_id))
    if share_id:
        for name, path in (
            ("disable_share", "share/disable"),
            ("enable_share", "share/enable"),
            ("get_share_info", "share/get"),
        ):
            params = {"id": share_id} if name != "get_share_info" else {"id": share_id}
            r = await safe(name, client.request("POST" if name != "get_share_info" else "GET", path, params=params))
            check(f"{name} (?id=)", r is not None)
        dele = await safe("delete_share", client.request("POST", "share/delete", params={"id": share_id}))
        check("delete_share (?id=)", dele is not None)

    # task listing of the upload (typed task API)
    tasks = await safe("list upload tasks", client.request("GET", "task/upload/done", params={"page": 1, "per_page": 50}))
    check("GET /task/upload/done", tasks is not None)

    # rename + remove (basic fs writes)
    renamed = await safe("rename", client.request("POST", "fs/rename", json={"path": hello, "name": "renamed.txt"}))
    check("rename hello.txt", renamed is not None)
    removed = await safe(
        "remove test dir",
        client.request("POST", "fs/remove", json={"dir": "/199", "names": [f"mcp-live-{ts}"]}),
    )
    check("cleanup test dir", removed is not None)

    await client.close()

    print("\n===== SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("Failed:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())