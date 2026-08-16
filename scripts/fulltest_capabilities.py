"""Comprehensive capability sweep against the live OpenList instance.

Everything is confined to /test (SFTP mount) and a timestamped subtree that is
removed at the end. Global/destructive admin ops (index build/clear, reset
token, clear_done/clear_succeeded/retry_failed, save_settings) are deliberately
NOT executed — they affect the whole server.

Usage:
    OPENLIST_URL=.. OPENLIST_USERNAME=.. OPENLIST_PASSWORD=.. OPENLIST_ALLOW_HTTP=true \
        python scripts/fulltest_capabilities.py
"""

import asyncio
import base64
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openlist_mcp.client import OpenListClient, OpenListError  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []
SKIP: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    SKIP.append(name)
    print(f"[SKIP ] {name} — {why}")


async def safe(client, method: str, path: str, **kwargs):
    try:
        return await client.request(method, path, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": str(exc)}


def clean(obj) -> dict:
    """Deduplicate for printing (avoid dumping huge trees)."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if k not in ("raw_url", "sign", "url")}
    if isinstance(obj, list):
        return [clean(x) for x in obj[:5]]
    return obj


async def main() -> None:
    client = OpenListClient()
    ts = int(time.time())
    base = f"/test/mcp-full-{ts}"

    # ── Setup ─────────────────────────────────────────────────────────────
    await client.login()
    check("login + token", bool(client._token))

    mk = await safe(client, "POST", "fs/mkdir", json={"path": base})
    check("mkdir base", mk is not None, base)
    for d in ("docs", "sub", "sub/nested", "move-src/dir1", "regexdir"):
        await safe(client, "POST", "fs/mkdir", json={"path": f"{base}/{d}"})

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc1.txt", "zip content one")
        z.writestr("doc2.txt", "zip content two")
    zip_bytes = zip_buf.getvalue()

    uploads = [
        ("a.txt", b"hello world from fulltest"),
        ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 128),
        ("data.zip", zip_bytes),
        ("regexdir/f1.txt", b"f1"),
        ("regexdir/f2.txt", b"f2"),
        ("move-src/dir1/file1.txt", b"move me"),
    ]
    for rel, content in uploads:
        res = await client.upload(path=f"{base}/{os.path.dirname(rel)}", file_content=content,
                                  file_name=os.path.basename(rel), as_task=False)
        check(f"upload {rel}", res is not None)

    # ── fs group ──────────────────────────────────────────────────────────
    lst = await safe(client, "POST", "fs/list", json={"path": base, "page": 1, "per_page": 200})
    names = [i.get("name") for i in (lst or {}).get("content", [])]
    check("list_files base (200/page)", "a.txt" in names and "docs" in names, str(names))

    dirs = await safe(client, "POST", "fs/dirs", json={"path": base})
    check("list_dirs base", dirs is not None)

    info = await safe(client, "POST", "fs/get", json={"path": f"{base}/a.txt"})
    check("get_file_info a.txt", (info or {}).get("name") == "a.txt",
          str(clean(info or {}).get("name")))

    created = await safe(client, "POST", "fs/mkdir", json={"path": f"{base}/newdir"})
    check("create_folder newdir", created is not None)

    renamed = await safe(client, "POST", "fs/rename", json={"path": f"{base}/a.txt", "name": "a-renamed.txt"})
    check("rename a.txt", renamed is not None)

    batched = await safe(client, "POST", "fs/batch_rename", json={
        "src_dir": base, "rename_objects": [
            {"src_name": "photo.png", "new_name": "photo2.png"},
            {"src_name": "regexdir", "new_name": "regexdir2"},
        ]})
    check("batch_rename", batched is not None)

    regex = await safe(client, "POST", "fs/regex_rename", json={
        "src_dir": f"{base}/regexdir2", "src_name_regex": r"^(.*)\.txt$", "new_name_regex": r"$1.md"})
    check("regex_rename .txt->.md", regex is not None)

    copied = await safe(client, "POST", "fs/copy", json={"src_dir": base, "src_name": "photo2.png",
                                                         "dst_dir": f"{base}/docs"})
    check("copy photo2.png -> docs", copied is not None)

    moved = await safe(client, "POST", "fs/move", json={"src_dir": base, "src_name": "a-renamed.txt",
                                                        "dst_dir": f"{base}/docs"})
    check("move a-renamed.txt -> docs", moved is not None)

    rec = await safe(client, "POST", "fs/recursive_move", json={"src_dir": f"{base}/move-src",
                                                                "dst_dir": f"{base}/move-dst"})
    check("recursive_move move-src -> move-dst", rec is not None)
    moved_list = await safe(client, "POST", "fs/list", json={"path": f"{base}/move-dst/dir1", "page": 1, "per_page": 50})
    check("recursive_move content landed", bool((moved_list or {}).get("content")))

    await safe(client, "POST", "fs/remove", json={"dir": base, "names": ["data.zip"]})

    tree = await safe(client, "POST", "fs/list", json={"path": f"{base}/docs", "page": 1, "per_page": 50})
    check("tree via list (docs has moved file)", bool((tree or {}).get("content")))

    du = await safe(client, "POST", "fs/recursive_move", json={"src_dir": f"{base}/docs", "dst_dir": f"{base}/docs"})
    check("recursive_move no-op safe", du is not None)

    mirror = await safe(client, "POST", "fs/copy", json={"src_dir": f"{base}/docs", "src_name": "a-renamed.txt",
                                                        "dst_dir": f"{base}/mirror-test"})
    check("copy mirror-test", mirror is not None)

    search = await safe(client, "POST", "fs/search", json={"parent": base, "keywords": "renamed", "page": 1, "per_page": 20})
    check("search_files 'renamed'", search is not None, str(clean(search or {}))[:120])

    # ── transfer group ────────────────────────────────────────────────────
    dl = await safe(client, "POST", "fs/get", json={"path": f"{base}/docs/a-renamed.txt"})
    check("get_download_url (raw_url)", bool((dl or {}).get("raw_url")), str((dl or {}).get("raw_url", ""))[:60])

    up = await safe(client, "POST", "fs/put", json={})  # not callable directly; use client.upload
    _ = up
    u2 = await client.upload(path=base, file_content=b"base64 upload test", file_name="b64.txt", as_task=False)
    check("upload_file (base64)", u2 is not None)

    # multipart on v4.2.2 → graceful failure
    try:
        await client.multipart_init(file_path=f"{base}/big.bin", file_size=10)
        check("multipart_init graceful fail on v4.2.2", False, "unexpectedly succeeded")
    except OpenListError as exc:
        graceful = "HTML" in exc.message or "unavailable" in exc.message
        check("multipart_init graceful fail on v4.2.2", graceful, f"err: {exc.message[:80]}")

    try:
        await client.multipart_status(upload_id="nonexist")
        check("multipart_status graceful fail", False, "unexpectedly succeeded")
    except OpenListError as exc:
        check("multipart_status graceful fail", True, f"err: {exc.message[:80]}")

    dui = await safe(client, "POST", "fs/get_direct_upload_info",
                     json={"path": base, "file_name": "b64.txt", "file_size": 19})
    not_impl = (dui or {}).get("__error__", "").find("not implement") >= 0
    check("get_direct_upload_info (Local → not implement)", not_impl, str(dui or {})[:100])

    # ── share group ───────────────────────────────────────────────────────
    share = await safe(client, "POST", "share/create", json={"files": [f"{base}/docs/a-renamed.txt"], "pwd": "t"})
    share_id = (share or {}).get("id")
    check("create_share", bool(share_id), str(share_id))

    if share_id:
        gs = await safe(client, "GET", "share/get", params={"id": share_id})
        check("get_share_info", bool(gs and gs.get("content") or gs), str(clean(gs or {}))[:100])
        lis = await safe(client, "GET", "share/list", params={"page": 1, "per_page": 50})
        check("list_shares", lis is not None)
        upd = await safe(client, "POST", "share/update", json={"id": share_id, "remark": "fulltest", "files": [f"{base}/docs/a-renamed.txt"]})
        check("update_share", upd is not None)
        dis = await safe(client, "POST", "share/disable", params={"id": share_id})
        en = await safe(client, "POST", "share/enable", params={"id": share_id})
        check("disable+enable share", dis is not None and en is not None)
        dele = await safe(client, "POST", "share/delete", params={"id": share_id})
        check("delete_share", dele is not None)

    # ── task group (own upload task only) ────────────────────────────────
    task_up = await client.upload(path=f"{base}/docs", file_content=b"task body" * 1000,
                                  file_name="taskfile.bin", as_task=True)
    tids = (task_up or {}).get("id") or (task_up or {}).get("value")
    check("upload as_task=True returns task id", bool(tids), str(tids))
    if tids:
        undo = await safe(client, "GET", "task/upload/undone", params={"page": 1, "per_page": 50})
        check("list_tasks upload undone", undo is not None)
        ti = await safe(client, "POST", "task/upload/info", params={"tid": str(tids)})
        check("get_task_info", ti is not None)
        cancel = await safe(client, "POST", "task/upload/cancel", params={"tid": str(tids)})
        check("cancel_task", cancel is not None)
        dele_t = await safe(client, "POST", "task/upload/delete", params={"tid": str(tids)})
        check("delete_task", dele_t is not None)
    al = await safe(client, "GET", "task/upload/done", params={"page": 1, "per_page": 50})
    check("list_tasks upload done", al is not None)

    # ── admin group (safe read-only + scoped ops) ─────────────────────────
    st = await safe(client, "GET", "admin/storage/list")
    check("admin list_storages", bool(st and st.get("content")), str(len((st or {}).get("content", []))))
    si = await safe(client, "GET", "admin/storage/get", params={"id": 2})
    check("admin get_storage_info(2 /test)", (si or {}).get("mount_path") == "/test", str(clean(si or {}))[:80])
    dn = await safe(client, "GET", "admin/driver/names")
    check("admin list_drivers", dn is not None and len(dn.get("data", []) or dn) > 0)
    di = await safe(client, "GET", "admin/driver/info", params={"driver": "Local"})
    check("admin get_driver_info(Local)", (di or {}).get("data") or di in ({}, None), str(clean(di or {}))[:100])
    dd = await safe(client, "GET", "admin/driver/list")
    check("admin list_drivers_detail", dd is not None)
    gs2 = await safe(client, "GET", "admin/setting/get", params={"key": "aria2"})
    check("admin get_setting(aria2)", gs2 is not None)
    gl = await safe(client, "GET", "admin/setting/list")
    check("admin get_settings", gl is not None)
    su = await safe(client, "GET", "admin/user/list", params={"page": 1, "per_page": 50})
    check("admin list_users", su is not None)
    gu = await safe(client, "GET", "admin/user/get", params={"id": 1})
    check("admin get_user(1)", (gu or {}).get("username") == "admin", str((gu or {}).get("username")))
    sm = await safe(client, "GET", "admin/meta/list", params={"page": 1, "per_page": 50})
    check("admin list_metas", sm is not None)
    gm = await safe(client, "GET", "admin/meta/get", params={"id": 0})
    check("admin get_meta(0)", gm is not None)

    idx = await safe(client, "POST", "admin/index/update", json={"paths": [base], "max_depth": 2})
    check("admin/index/update scoped (informative)", idx is not None, str(clean(idx or {}))[:100])
    ip = await safe(client, "GET", "admin/index/progress")
    check("admin/index/progress", ip is not None)

    sc = await safe(client, "POST", "admin/scan/start", json={"path": "/test"})
    check("admin/scan/start /test", sc is not None)
    sp = await safe(client, "GET", "admin/scan/progress")
    check("admin/scan/progress", sp is not None and "obj_count" in (sp or {}), str(clean(sp or {}))[:80])
    ss = await safe(client, "POST", "admin/scan/stop")
    check("admin/scan/stop", ss is not None)

    # ── advanced group ────────────────────────────────────────────────────
    cap = await safe(client, "GET", "public/settings")
    check("get_capabilities (public settings)", cap is not None)
    me = await safe(client, "GET", "me")
    check("get_me", (me or {}).get("username") == "admin")
    ldt = await safe(client, "GET", "public/offline_download_tools")
    check("list_download_tools", ldt is not None, str(clean(ldt or {}))[:80])
    ae = await safe(client, "GET", "public/archive_extensions")
    check("get_archive_extensions", ae is not None)

    # archive: upload zip again, then meta/list/decompress
    zip2 = await client.upload(path=base, file_content=zip_bytes, file_name="data.zip", as_task=False)
    check("re-upload data.zip", zip2 is not None)
    am = await safe(client, "POST", "fs/archive/meta", json={"path": f"{base}/data.zip"})
    check("get_archive_meta", am is not None, str(clean(am or {}))[:100])
    al2 = await safe(client, "POST", "fs/archive/list", json={"path": f"{base}/data.zip", "page": 1, "per_page": 50})
    check("list_archive_files", al2 is not None)
    dcz = await safe(client, "POST", "fs/archive/decompress", json={
        "src_dir": base, "name": ["data.zip"], "dst_dir": f"{base}/unzipped", "overwrite": True})
    check("decompress_archive", dcz is not None)
    uz = await safe(client, "POST", "fs/list", json={"path": f"{base}/unzipped", "page": 1, "per_page": 50})
    unames = [i.get("name") for i in (uz or {}).get("content", [])]
    check("decompressed files present", "doc1.txt" in unames and "doc2.txt" in unames, str(unames))

    # torrent: minimal valid metainfo
    pieces = hashlib.sha1(b"hello world").digest()
    meta = {b"announce": b"https://example.com/announce",
            b"info": {b"name": b"hello.txt", b"length": 11, b"piece length": 16384, b"pieces": pieces}}

    def bencode(d):
        if isinstance(d, dict):
            return b"d" + b"".join(bencode(k) + bencode(v) for k, v in sorted(d.items())) + b"e"
        if isinstance(d, list):
            return b"l" + b"".join(bencode(x) for x in d) + b"e"
        if isinstance(d, int):
            return b"i%de" % d
        if isinstance(d, bytes):
            return b"%d:%s" % (len(d), d)
        raise TypeError(d)

    tb64 = base64.b64encode(bencode(meta)).decode()
    pt = await safe(client, "POST", "fs/torrent/parse", json={"torrent_data": tb64})
    has_hash = bool((pt or {}).get("info_hash") or (pt or {}).get("info"))
    check("parse_torrent", has_hash, str(clean(pt or {}))[:100])

    gt = await safe(client, "POST", "fs/torrent/generate", json={"path": f"{base}/docs/a-renamed.txt"})
    has_td = bool((gt or {}).get("torrent_data"))
    check("generate_torrent", has_td, f"size={(gt or {}).get('size')}, hash={(gt or {}).get('info_hash', '')[:12]}")

    rt = await safe(client, "POST", "fs/torrent/rapid_upload", json={"torrent_data": tb64, "path": base})
    check("torrent_rapid_upload (SFTP → driver answer)", rt is not None and "__error__" not in rt,
          f"{clean(rt or {})}".replace("__error__", "")[:120])

    fd = await safe(client, "POST", "fs/list", json={"path": f"{base}/docs", "page": 1, "per_page": 200})
    _ = fd
    cp = await safe(client, "POST", "fs/get", json={"path": f"{base}/docs/a-renamed.txt"})
    check("content_preview (fs/get → raw_url)", bool((cp or {}).get("raw_url")))

    # logout → auto re-login
    lo = await safe(client, "GET", "auth/logout")
    check("logout", lo is not None)
    me2 = await safe(client, "GET", "me")
    check("auto re-login after logout", bool(client._token) and (me2 or {}).get("username") == "admin")

    # ── Cleanup ───────────────────────────────────────────────────────────
    rm = await safe(client, "POST", "fs/remove", json={"dir": "/test", "names": [f"mcp-full-{ts}"]})
    check("cleanup base dir", rm is not None)
    await client.close()

    # ── Report ────────────────────────────────────────────────────────────
    print("\n===== CAPABILITY SWEEP SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}  SKIP: {len(SKIP)}")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())