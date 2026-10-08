"""Verify the READONLY and ALLOWED_PATHS safety gates against the live instance.

Run twice with different env:
  TEST_MODE=readonly OPENLIST_READONLY=true
      → every write tool must be rejected client-side
  TEST_MODE=allowed_paths OPENLIST_ALLOWED_PATHS=$OPENLIST_TEST_DIR \
      OPENLIST_BLOCKED_PATH=/elsewhere
      → writes outside the allowlist must raise PermissionError, writes inside must work
"""

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openlist_mcp.tools.admin import register_admin_tools  # noqa: E402
from openlist_mcp.tools.advanced import register_advanced_tools  # noqa: E402
from openlist_mcp.tools.auth import register_auth_tools, register_public_tools  # noqa: E402
from openlist_mcp.tools.fs import register_fs_tools  # noqa: E402
from openlist_mcp.tools.share import register_share_tools  # noqa: E402
from openlist_mcp.tools.task import register_task_tools  # noqa: E402
from openlist_mcp.tools.transfer import register_transfer_tools  # noqa: E402

MODE = os.environ.get("TEST_MODE", "readonly")

# A disposable directory inside a writable mount, and the allowlist target.
# Required, not defaulted: these checks create and delete files.
TEST_DIR = os.environ.get("OPENLIST_TEST_DIR", "").strip().rstrip("/")
if not TEST_DIR:
    raise SystemExit(
        "OPENLIST_TEST_DIR is required: point it at a disposable directory inside a "
        "writable mount, e.g. OPENLIST_TEST_DIR=/scratch/mcp (the server root is refused)."
    )

# A path the allowlist must reject. Only allowed_paths mode needs it, and every
# operation aimed at it is supposed to fail before reaching the server.
BLOCKED_DIR = os.environ.get("OPENLIST_BLOCKED_PATH", "").strip().rstrip("/")
if MODE == "allowed_paths" and not BLOCKED_DIR:
    raise SystemExit(
        "OPENLIST_BLOCKED_PATH is required in allowed_paths mode: give a path outside "
        "OPENLIST_ALLOWED_PATHS, e.g. OPENLIST_BLOCKED_PATH=/other-mount."
    )


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
    tools = r.tools
    passed = failed = 0

    async def one(label: str, fn, expect: str = "PermissionError"):
        nonlocal passed, failed
        try:
            out = await fn()
            text = out if isinstance(out, str) else json.dumps(out)
            ok = text.startswith(expect)
            print(f"[{'PASS' if ok else 'FAIL'}] {label}: {text[:70]}")
        except PermissionError as exc:
            ok = expect == "PermissionError"
            print(f"[{'PASS' if ok else 'FAIL'}] {label}: PermissionError: {str(exc)[:60]}")
        except Exception as exc:  # noqa: BLE001
            ok = expect == str(type(exc).__name__)
            print(f"[{'PASS' if ok else 'FAIL'}] {label}: {type(exc).__name__}: {str(exc)[:60]}")
        passed += ok
        failed += not ok

    if MODE == "readonly":
        await one(
            "create_folder (readonly)",
            lambda: tools["create_folder"](path=f"{TEST_DIR}/readonly-check"),
        )
        await one(
            "rename (readonly)", lambda: tools["rename"](path=f"{TEST_DIR}/s.txt", name="x.txt")
        )
        await one(
            "remove (readonly)",
            lambda: tools["remove"](directory=TEST_DIR, names=["s.txt"], confirm=True),
        )
        await one(
            "upload_file (readonly)",
            lambda: tools["upload_file"](
                path=TEST_DIR, file_name="x.txt", file_content_base64="aGk=", as_task=False
            ),
        )
        await one(
            "move (readonly)",
            lambda: tools["move"](src_dir=TEST_DIR, dst_dir=f"{TEST_DIR}/docs", names=["s.txt"]),
        )
        await one(
            "copy (readonly)",
            lambda: tools["copy"](src_dir=TEST_DIR, dst_dir=f"{TEST_DIR}/docs", names=["s.txt"]),
        )
        await one(
            "share write (readonly)", lambda: tools["create_share"](files=[f"{TEST_DIR}/s.txt"])
        )
        # Tools that hand out upload credentials or write a .torrent are writes too:
        # a read-only mode that let them through would still mutate the server.
        await one(
            "get_direct_upload_info (readonly)",
            lambda: tools["get_direct_upload_info"](path=TEST_DIR, file_name="x.bin", file_size=10),
        )
        await one(
            "generate_torrent (readonly)",
            lambda: tools["generate_torrent"](path=f"{TEST_DIR}/s.txt"),
        )
        await one(
            "torrent_rapid_upload (readonly)",
            lambda: tools["torrent_rapid_upload"](torrent_data="eA==", path=TEST_DIR),
        )
        await one(
            "read still allowed (readonly)",
            lambda: tools["list_files"](path=TEST_DIR, per_page=5),
            expect="",
        )
        # Reading a file is not a write, so no gate rejects its URL. The path may
        # not exist — every write in this mode was blocked — and a missing-object
        # error still proves the gate stayed out of the way, while a gate rejection
        # would surface as PermissionError.
        try:
            await tools["get_download_url"](path=f"{TEST_DIR}/s.txt")
            passed += 1
            print("[PASS] get_download_url not gated (readonly)")
        except PermissionError as exc:
            failed += 1
            print(f"[FAIL] get_download_url not gated (readonly): {str(exc)[:60]}")
        except Exception as exc:  # noqa: BLE001
            passed += 1
            print(
                f"[PASS] get_download_url not gated (readonly): "
                f"reached the server ({type(exc).__name__})"
            )
    elif MODE == "allowed_paths":
        await one(
            "mkdir outside allowlist (write)",
            lambda: tools["create_folder"](path=f"{BLOCKED_DIR}/blocked"),
        )
        await one(
            "remove outside allowlist",
            lambda: tools["remove"](directory=BLOCKED_DIR, names=["x"], confirm=True),
        )
        await one(
            "upload outside allowlist",
            lambda: tools["upload_file"](
                path=BLOCKED_DIR, file_name="x.txt", file_content_base64="aGk=", as_task=False
            ),
        )
        await one(
            "list inside allowlist",
            lambda: tools["list_files"](path=TEST_DIR, per_page=5),
            expect="",
        )
        await one(
            "create_folder inside allowlist",
            lambda: tools["create_folder"](path=f"{TEST_DIR}/gate-check"),
            expect="",
        )
        # The allowlist has to reach the tools that trade in URLs and credentials,
        # not just the ones that take a path and write to it: a download URL or a
        # direct-upload capability for an outside path is itself the leak.
        await one(
            "get_download_url outside allowlist",
            lambda: tools["get_download_url"](path=f"{BLOCKED_DIR}/x.txt"),
        )
        await one(
            "get_direct_upload_info outside allowlist",
            lambda: tools["get_direct_upload_info"](
                path=BLOCKED_DIR, file_name="x.bin", file_size=10
            ),
        )
        await one(
            "generate_torrent outside allowlist",
            lambda: tools["generate_torrent"](path=f"{BLOCKED_DIR}/x.txt"),
        )
        await one(
            "content_preview outside allowlist",
            lambda: tools["content_preview"](path=f"{BLOCKED_DIR}/x.txt"),
        )
        # cleanup the dir created in the allowed test
        with contextlib.suppress(Exception):
            await tools["remove"](directory=TEST_DIR, names=["gate-check"], confirm=True)

    print(f"\n===== {MODE.upper()} GATE SUMMARY =====  PASS: {passed}  FAIL: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
