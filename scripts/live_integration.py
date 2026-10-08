#!/usr/bin/env python3
"""OpenList MCP Server live integration smoke test.

Set environment variables before running:
    export OPENLIST_URL="https://your-openlist.example.com"
    export OPENLIST_USERNAME="your_username"
    export OPENLIST_PASSWORD="your_password"
    export OPENLIST_TEST_DIR="/scratch/mcp"  # required: a disposable directory inside a writable mount
"""

import asyncio
import os
import time

from openlist_mcp.client import OpenListError, get_client

# Required, not defaulted: this smoke test creates and deletes a folder, so an
# unset target would write to the server root.
TEST_DIR = os.environ.get("OPENLIST_TEST_DIR", "").strip().rstrip("/")
if not TEST_DIR:
    raise SystemExit(
        "OPENLIST_TEST_DIR is required: point it at a disposable directory inside a "
        "writable mount, e.g. OPENLIST_TEST_DIR=/scratch/mcp (the server root is refused)."
    )
TEST_FOLDER = f"mcp-test-{int(time.time())}"
TEST_PATH = f"{TEST_DIR}/{TEST_FOLDER}"


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def print_success(msg: str) -> None:
    print(f"{Colors.GREEN}PASS{Colors.RESET} {msg}")


def print_error(msg: str) -> None:
    print(f"{Colors.RED}FAIL{Colors.RESET} {msg}")


def print_info(msg: str) -> None:
    print(f"{Colors.BLUE}INFO{Colors.RESET} {msg}")


def print_warn(msg: str) -> None:
    print(f"{Colors.YELLOW}WARN{Colors.RESET} {msg}")


def require_env() -> bool:
    missing = [
        k
        for k in ("OPENLIST_URL", "OPENLIST_USERNAME", "OPENLIST_PASSWORD")
        if not os.environ.get(k)
    ]
    if missing:
        print_error("Missing required environment variables: " + ", ".join(missing))
        return False
    return True


async def run_test(name: str, func) -> bool:
    print("\n" + "=" * 50)
    print(name)
    print("=" * 50)
    try:
        await func()
        print_success(name)
        return True
    except OpenListError as e:
        print_error(f"{name}: {e.message}")
        return False
    except Exception as e:
        print_error(f"{name}: {e}")
        return False


async def main() -> int:
    if not require_env():
        return 2

    client = await get_client()
    results: list[tuple[str, bool]] = []

    async def login():
        await client.login()
        print_info("Login successful; token acquired but not printed.")

    async def list_files():
        data = await client.request("POST", "fs/list", json={"path": TEST_DIR})
        print_info(f"Listed {len(data.get('content', []))} entries in {TEST_DIR}")

    async def create_folder():
        await client.request("POST", "fs/mkdir", json={"path": TEST_PATH})
        info = await client.request("POST", "fs/get", json={"path": TEST_PATH})
        if not info.get("is_dir"):
            raise RuntimeError("created path is not a directory")
        print_info(f"Created and verified {TEST_PATH}")

    async def public_settings():
        data = await client.request("GET", "public/settings", require_auth=False)
        print_info(f"Received {len(data)} public settings")

    async def list_shares():
        data = await client.request("GET", "share/list")
        print_info(f"Share response keys: {', '.join(data.keys()) or '(empty)'}")

    async def list_tasks():
        data = await client.request("GET", "task/offline_download/done")
        print_info(f"Offline download task response keys: {', '.join(data.keys()) or '(empty)'}")

    for name, func in [
        ("Login", login),
        ("List files", list_files),
        ("Create folder", create_folder),
        ("Public settings", public_settings),
        ("List shares", list_shares),
        ("List offline download tasks", list_tasks),
    ]:
        results.append((name, await run_test(name, func)))

    print("\n" + "=" * 50)
    print("Cleanup")
    print("=" * 50)
    try:
        await client.request("POST", "fs/remove", json={"dir": TEST_DIR, "names": [TEST_FOLDER]})
        print_success(f"Deleted {TEST_PATH}")
    except Exception as e:
        print_warn(f"Cleanup failed: {e}")

    passed = sum(1 for _, ok in results if ok)
    print("\n" + "=" * 50)
    print(f"Result: {passed}/{len(results)} passed")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
