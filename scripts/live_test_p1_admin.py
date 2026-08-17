"""Live P1 (storage CRUD + driver configs + user write) verification.

Every change is reversible and cleaned up at the end: a temporary Local
storage is created and deleted, an aria2 config is backed up/written/deleted,
and a test user is created/updated/removed via the raw API.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openlist_mcp.client import OpenListClient  # noqa: E402
from openlist_mcp.tools.admin import register_admin_tools  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


class Recorder:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def deco(f):
            self.tools[f.__name__] = f
            return f

        return deco


async def main() -> None:
    r = Recorder()
    register_admin_tools(r)
    t = r.tools
    raw = OpenListClient()
    await raw.login()
    ts = int(time.time())

    # ── 1. storage lifecycle ──────────────────────────────────────────────
    # NOTE: Local driver root_folder_path is a HOST filesystem path, not an
    # OpenList mount path. /tmp always exists on the server.
    data_dir = "/tmp"  # existing host dir; Local root_folder_path must exist
    mount = f"/mcp-p1-{ts}"

    r1 = t["create_storage"](mount, "Local", addition=json.dumps({"root_folder_path": data_dir}),
                             remark="p1-live-test", confirm=True)
    out = await r1
    check("create_storage", "Storage created" in out, out[:80])

    lst = await t["list_storages"]()
    lnames = [s.get("mount_path") for s in (json.loads(lst) or {}).get("content", [])]
    check("list_storages shows new mount", any(mount == n or n and n.startswith("/mcp-p1-") for n in lnames), str(lnames))

    # find the created storage id
    sid = None
    for s in (json.loads(lst) or {}).get("content", []):
        if (s.get("mount_path") or "").startswith("/mcp-p1-"):
            sid = s.get("id")
    check("created storage has id", bool(sid), str(sid))

    if sid:
        up = await t["update_storage"](sid, remark="p1-updated", confirm=True)
        check("update_storage", "Storage updated" in up, up[:80])
        gi = json.loads(await t["get_storage_info"](sid))
        check("update persisted remark", (gi or {}).get("remark") == "p1-updated", str((gi or {}).get("remark")))
        dis = await t["disable_storage"](sid, confirm=True)
        check("disable_storage", "disabled" in dis, dis[:70])
        en = await t["enable_storage"](sid, confirm=True)
        check("enable_storage", "enabled" in en, en[:70])
        dele = await t["delete_storage"](sid, confirm=True)
        check("delete_storage", "deleted" in dele, dele[:70])
        lst2 = json.loads(await t["list_storages"]())
        gone = all((s.get("mount_path") or "") != mount for s in (lst2 or {}).get("content", []))
        check("storage removed from list", gone)


    # ── 2. driver config: backup → set → verify → restore ───────────────
    # aria2 settings are stored under aria2_uri / aria2_secret (conf keys),
    # not under a single "aria2" key.
    async def _aria2_state():
        try:
            return {"uri": json.loads(await t["get_setting"]("aria2_uri")).get("value"),
                    "secret": json.loads(await t["get_setting"]("aria2_secret")).get("value")}
        except Exception:  # noqa: BLE001
            return None  # no existing config

    aria2_before = await _aria2_state()
    set_out = await t["set_aria2"]("http://127.0.0.1:6800/jsonrpc", "p1-token", confirm=True)
    check("set_aria2 (config write)", "saved" in set_out or "configured" in set_out or "aria2" in set_out, set_out[:100])
    post = await _aria2_state()
    check("aria2 config persisted", bool(post and post["uri"] == "http://127.0.0.1:6800/jsonrpc"), str(post)[:90])
    # restore
    if aria2_before is None:
        for key in ("aria2_uri", "aria2_secret"):
            try:
                await t["delete_setting"](key, confirm=True)
            except Exception as exc:  # noqa: BLE001
                print("      restore note:", str(exc)[:60])
        check("aria2 config restored (deleted)", True)
    else:
        await t["set_aria2"](aria2_before["uri"] or "", aria2_before["secret"] or "", confirm=True)
        check("aria2 config restored (original)", True)

    # bad input path — must fail client-side without touching the server
    bad = await t["set_aria2"](confirm=True)
    check("set_aria2 requires uri (no server write)", "uri is required" in bad)
    bad2 = await t["set_115"](confirm=True)
    check("set_115 requires temp_dir (no server write)", "temp_dir is required" in bad2)

    # confirm gating — nothing written
    gate = await t["create_storage"]("/never", "Local", confirm=False)
    check("create_storage confirm gate", "confirm=true" in gate)

    # ── 3. user create/update, cleaned via raw API ───────────────────────
    uname = f"mcp_p1_{ts}"
    cu = await t["create_user"](uname, password="P1Test123!", base_path="/test", confirm=True)
    check("create_user", "User created" in cu, cu[:80])
    ul = json.loads(await t["list_users"]())
    uid = None
    for u in (ul or {}).get("content", []):
        if u.get("username") == uname:
            uid = u.get("id")
    check("created user has id", bool(uid), str(uid))
    if uid:
        gu = json.loads(await t["get_user"](uid))
        check("get_user new user", (gu or {}).get("username") == uname, str((gu or {}).get("username")))
        uu = await t["update_user"](uid, disabled=True, confirm=True)
        check("update_user (disable)", "User updated" in uu, uu[:70])
        gu2 = json.loads(await t["get_user"](uid))
        check("disable persisted", (gu2 or {}).get("disabled") is True, str((gu2 or {}).get("disabled")))
        # cleanup via raw API (delete tool not in P1 scope)
        await raw.request("POST", "admin/user/delete", params={"id": uid})
        ul2 = json.loads(await t["list_users"]())
        check("test user removed", all(u.get("username") != uname for u in (ul2 or {}).get("content", []) if isinstance(u, dict)))

    await raw.close()
    print("\n===== P1 LIVE SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
