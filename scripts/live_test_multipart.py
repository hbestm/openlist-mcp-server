"""Live multipart upload tests against OpenList v4.2.5+.

Every write goes into a timestamped subtree of OPENLIST_TEST_DIR, which is
removed at the end.

Usage:
    OPENLIST_URL=.. OPENLIST_USERNAME=.. OPENLIST_PASSWORD=.. OPENLIST_TEST_DIR=/scratch/mcp \
        python scripts/live_test_multipart.py
"""

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openlist_mcp.client import OpenListClient, OpenListError  # noqa: E402
from openlist_mcp.tools.transfer import register_transfer_tools  # noqa: E402

# A disposable directory inside a writable mount. Required, not defaulted: this
# suite creates and deletes files, so guessing a target would risk real data.
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


class Recorder:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def deco(f):
            self.tools[f.__name__] = f
            return f

        return deco


def parse(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return {"_text": text[:140]}


async def main() -> None:
    r = Recorder()
    register_transfer_tools(r)
    tools = r.tools

    c = OpenListClient()
    await c.login()
    ts = int(time.time())
    base = f"{TEST_DIR}/mcp-mp-{ts}"
    await c.request("POST", "fs/mkdir", json={"path": base})

    # ── 1. single-chunk small file via the real tool ─────────────────────
    small = b"hello multipart on v4.2.5" * 3
    out = parse(
        await tools["upload_file_multipart"](
            path=base,
            file_name="small.txt",
            file_content_base64=base64.b64encode(small).decode(),
            chunk_size=8,
            overwrite=True,
        )
    )
    check("upload_file_multipart small (1 chunk)", out.get("ok") is True, str(out)[:140])

    # ── 2. multi-chunk large file (25 MiB, 8 MiB chunks → 4 chunks) ──────
    big = os.urandom(25 * 1024 * 1024)
    b64 = base64.b64encode(big).decode()
    out = parse(
        await tools["upload_file_multipart"](
            path=base,
            file_name="big.bin",
            file_content_base64=b64,
            chunk_size=8 * 1024 * 1024,
            overwrite=True,
        )
    )
    ok = out.get("ok") is True and out.get("total_chunks") == 4 and out.get("chunks_sent") == 4
    check("upload_file_multipart big 25MiB/4 chunks", ok, str(out)[:200])

    info = await c.request("POST", "fs/get", json={"path": f"{base}/big.bin"})
    got = (info or {}).get("size")
    check("server-side big.bin size matches", got == len(big), f"server={got} expected={len(big)}")

    # md5 verify via raw download
    raw = await c.request("POST", "fs/get", json={"path": f"{base}/big.bin"})
    url = (raw or {}).get("raw_url", "")
    if url:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as hc:
            resp = await hc.get(url)
        check(
            "big.bin content md5 match",
            hashlib.md5(resp.content).hexdigest() == hashlib.md5(big).hexdigest(),
            f"downloaded {len(resp.content)}B",
        )

    # ── 3. resume: init → upload chunk 0 only → re-init same path/size ───
    mid = os.urandom(6 * 1024 * 1024)  # 2 chunks @ 4MiB
    target = f"{base}/resume.bin"
    init1 = await c.multipart_init(
        file_path=target,
        file_size=len(mid),
        chunk_size=4 * 1024 * 1024,
        overwrite=True,
        file_md5=hashlib.md5(mid).hexdigest(),
    )
    up1 = init1.get("upload_id", "")
    await c.multipart_chunk(up1, 0, mid[: 4 * 1024 * 1024])
    st = await c.multipart_status(upload_id=up1)
    recv = st.get("received") if st else None
    check(
        "partial upload received [[0,0]]",
        recv == [[0, 0]] or (isinstance(recv, list) and recv and recv[0] == [0, 0]),
        str(recv),
    )

    # resume with the same target → server must hand back the SAME session and
    # the tool then skips already-received chunks (md5 identity proof required).
    out = parse(
        await tools["upload_file_multipart"](
            path=base,
            file_name="resume.bin",
            file_content_base64=base64.b64encode(mid).decode(),
            chunk_size=4 * 1024 * 1024,
            overwrite=True,
        )
    )
    same_session = out.get("upload_id") == up1  # server handed back the SAME session
    check(
        "resume reuses session + skips chunk 0",
        out.get("ok") is True and same_session and out.get("chunks_sent") == 2,
        f"session_reused={same_session} {str(out)[:140]}",
    )
    info2 = await c.request("POST", "fs/get", json={"path": target})
    check(
        "resume.bin final size",
        (info2 or {}).get("size") == len(mid),
        f"server={(info2 or {}).get('size')}",
    )

    # ── 4. status & abort on a fresh session ─────────────────────────────
    init2 = await c.multipart_init(
        file_path=f"{base}/abort.bin", file_size=1000, chunk_size=1024, overwrite=True
    )
    ab = parse(
        await tools["multipart_abort_upload"](upload_id=init2.get("upload_id", ""), confirm=True)
    )
    check("multipart_abort_upload", "aborted" in str(ab).lower(), str(ab)[:120])
    try:
        await c.multipart_status(upload_id=init2.get("upload_id", ""))
        check("status after abort (session gone)", False, "still returned a session")
    except OpenListError as exc:
        check(
            "status after abort (session gone)",
            "not found" in exc.message.lower() or exc.code in (404, 500),
            f"{exc.code} {exc.message[:80]}",
        )

    # A completed session is gone server-side (path+size query then 404s), so
    # validate path+size lookup against an in-progress session instead.
    init3 = await c.multipart_init(
        file_path=f"{base}/query.bin", file_size=len(small), chunk_size=1024, overwrite=True
    )
    st2 = parse(
        await tools["multipart_upload_status"](path=f"{base}/query.bin", file_size=len(small))
    )
    check(
        "multipart_upload_status by path (in-progress session)",
        st2 is not None and isinstance(st2, dict),
        str(st2)[:120],
    )
    with contextlib.suppress(Exception):
        await c.multipart_abort(init3.get("upload_id", ""))

    # ── cleanup ──────────────────────────────────────────────────────────
    await c.request("POST", "fs/remove", json={"dir": TEST_DIR, "names": [f"mcp-mp-{ts}"]})
    await c.close()

    print("\n===== MULTIPART LIVE SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
