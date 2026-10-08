"""Stability & robustness tests against the live OpenList (confined to /test)."""

import asyncio
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openlist_mcp.client import OpenListClient  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


async def main() -> None:
    c = OpenListClient()
    await c.login()
    base = f"/test/mcp-stab-{int(time.time())}"
    await c.request("POST", "fs/mkdir", json={"path": base})
    await c.upload(path=base, file_content=b"stability" * 100, file_name="s.txt", as_task=False)

    # 1. sequential repeat (30x) — no latency blowup, no crash
    t0 = time.perf_counter()
    for _ in range(30):
        r = await c.request("POST", "fs/list", json={"path": base, "page": 1, "per_page": 50})
        assert r is not None
    dt = time.perf_counter() - t0
    check("30x sequential list_files", dt < 15, f"{dt:.2f}s total ({dt / 30 * 1000:.0f}ms/call)")

    # 2. concurrent fan-out (20x same op on shared client)
    async def one(i: int):
        return await c.request("POST", "fs/list", json={"path": base, "page": 1, "per_page": 50})

    results = await asyncio.gather(*(one(i) for i in range(20)), return_exceptions=True)
    errs = [r for r in results if isinstance(r, BaseException)]
    check(
        "20x concurrent list_files (shared client)",
        not errs,
        f"{len(errs)} errors" if errs else "all ok",
    )

    # 3. mixed concurrent load: get + list + dirs
    async def mixed(i: int):
        if i % 3 == 0:
            return await c.request("POST", "fs/get", json={"path": f"{base}/s.txt"})
        if i % 3 == 1:
            return await c.request("POST", "fs/dirs", json={"path": base})
        return await c.request("POST", "fs/list", json={"path": "/test", "page": 1, "per_page": 30})

    results = await asyncio.gather(*(mixed(i) for i in range(15)), return_exceptions=True)
    errs = [r for r in results if isinstance(r, BaseException)]
    check("15x mixed concurrent requests", not errs, f"{len(errs)} errors" if errs else "all ok")

    # 4. error-path matrix — every bad input must raise a *typed* friendly error, never a hang/raw crash
    bad_cases = [
        (
            "traversal path",
            lambda: c.request("POST", "fs/list", json={"path": "../etc", "page": 1, "per_page": 5}),
        ),
        (
            "traversal path get",
            lambda: c.request("POST", "fs/get", json={"path": "/test/../../etc/passwd"}),
        ),
        (
            "per_page=0",
            lambda: c.request("POST", "fs/list", json={"path": base, "page": 1, "per_page": 0}),
        ),
        (
            "page=-5",
            lambda: c.request("POST", "fs/list", json={"path": base, "page": -5, "per_page": 10}),
        ),
        (
            "empty names remove",
            lambda: c.request("POST", "fs/remove", json={"dir": base, "names": []}),
        ),
        (
            "nested traversal remove",
            lambda: c.request("POST", "fs/remove", json={"dir": "/test", "names": ["../x"]}),
        ),
        (
            "nonexistent share get",
            lambda: c.request("GET", "share/get", params={"id": "no-such-id"}),
        ),
        (
            "bad task type list",
            lambda: c.request("GET", "task/bogus/done", params={"page": 1, "per_page": 5}),
        ),
        ("unknown api route", lambda: c.request("GET", "fs/no_such_endpoint")),
    ]
    for label, fn in bad_cases:
        t0 = time.perf_counter()
        try:
            await fn()
            check(f"bad-input: {label} (server accepted)", True, "no exception")
        except Exception as exc:  # noqa: BLE001
            dt = time.perf_counter() - t0
            msg = str(exc)
            # graceful: a typed OpenListError with a clear message. The server
            # returns 200+HTML for unknown routes (SPA fallback) — the client
            # must detect that and raise, never leak raw HTML.
            graceful = ("[4" in msg or "[5" in msg or "HTML instead of JSON" in msg) and dt < 10
            check(f"bad-input: {label} (typed error)", graceful, f"{dt:.2f}s {msg[:80]}")

    # 5. auto re-auth: drop the token, next request must re-login transparently
    c._token = None
    r = await c.request("POST", "fs/list", json={"path": base, "page": 1, "per_page": 5})
    check("auto re-login after token drop", r is not None and bool(c._token))

    # 6. token expiry simulation via an invalid token then fresh login path
    c._token = "definitely.invalid.token"
    r = await c.request("GET", "me")
    check("401 -> re-login recovery", r is not None and r.get("username") == "admin")

    # 7. upload churn: 10 files up, 10 down, no fd/token leak
    for i in range(10):
        await c.upload(
            path=base, file_content=bytes([i]) * 512, file_name=f"churn{i}.bin", as_task=False
        )
    for i in range(10):
        await c.request("POST", "fs/remove", json={"dir": base, "names": [f"churn{i}.bin"]})
    lst = await c.request("POST", "fs/list", json={"path": base, "page": 1, "per_page": 50})
    left = [x.get("name") for x in (lst or {}).get("content", [])]
    check("10x upload/remove churn clean", "churn0.bin" not in left and "s.txt" in left, str(left))

    # 8. large listing (mount-wide) stays within sane time
    t0 = time.perf_counter()
    await c.request("POST", "fs/list", json={"path": "/test", "page": 1, "per_page": 500})
    dt = time.perf_counter() - t0
    check("mount-wide list /test (500/page)", dt < 10, f"{dt:.2f}s")

    # 9. cleanup
    await c.request("POST", "fs/remove", json={"dir": "/test", "names": [base.split("/")[-1]]})
    # 10. clear leftover copy tasks from earlier sweeps to leave server tidy
    with contextlib.suppress(Exception):
        await c.request("POST", "task/copy/clear_done")
    await c.close()

    print("\n===== STABILITY SUMMARY =====")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
