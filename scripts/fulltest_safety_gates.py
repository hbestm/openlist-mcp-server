"""Verify the READONLY and ALLOWED_PATHS safety gates against the live instance.

Run twice with different env:
  TEST_MODE=readonly OPENLIST_READONLY=true        → all write tools must be rejected client-side
  TEST_MODE=allowed_paths OPENLIST_ALLOWED_PATHS=/test → outside /test must raise PermissionError,
                                                          inside /test must work
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
            "create_folder (readonly)", lambda: tools["create_folder"](path="/test/readonly-check")
        )
        await one("rename (readonly)", lambda: tools["rename"](path="/test/s.txt", name="x.txt"))
        await one(
            "remove (readonly)",
            lambda: tools["remove"](directory="/test", names=["s.txt"], confirm=True),
        )
        await one(
            "upload_file (readonly)",
            lambda: tools["upload_file"](
                path="/test", file_name="x.txt", file_content_base64="aGk=", as_task=False
            ),
        )
        await one(
            "move (readonly)",
            lambda: tools["move"](src_dir="/test", dst_dir="/test/docs", names=["s.txt"]),
        )
        await one(
            "copy (readonly)",
            lambda: tools["copy"](src_dir="/test", dst_dir="/test/docs", names=["s.txt"]),
        )
        await one("share write (readonly)", lambda: tools["create_share"](files=["/test/s.txt"]))
        await one(
            "read still allowed (readonly)",
            lambda: tools["list_files"](path="/test", per_page=5),
            expect="",
        )
    elif MODE == "allowed_paths":
        await one(
            "mkdir outside allowlist (write)", lambda: tools["create_folder"](path="/199/blocked")
        )
        await one(
            "remove outside allowlist",
            lambda: tools["remove"](directory="/199", names=["x"], confirm=True),
        )
        await one(
            "upload outside allowlist",
            lambda: tools["upload_file"](
                path="/199", file_name="x.txt", file_content_base64="aGk=", as_task=False
            ),
        )
        await one(
            "list inside allowlist",
            lambda: tools["list_files"](path="/test", per_page=5),
            expect="",
        )
        await one(
            "create_folder inside allowlist",
            lambda: tools["create_folder"](path="/test/gate-check"),
            expect="",
        )
        # cleanup the dir created in the allowed test
        with contextlib.suppress(Exception):
            await tools["remove"](directory="/test", names=["gate-check"], confirm=True)

    print(f"\n===== {MODE.upper()} GATE SUMMARY =====  PASS: {passed}  FAIL: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
