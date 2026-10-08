#!/usr/bin/env python3
"""Cut a release: bump, tag, push that tag, then finish the GitHub release.

Mechanical, but easy to get wrong by hand — and two of the steps have bitten this
project for real. Pushing several tags in one `git push` does not fire the release
workflow, so the release silently never happens; and the workflow's own notes list
only merged pull requests, so a release built from direct commits lands with a body
that says nothing about what changed.

Write the CHANGELOG entry first. This script refuses to release a version the
CHANGELOG does not describe, then:

  1. bump `pyproject.toml`
  2. regenerate the documentation projections (the version table gains its row)
  3. run the gates — ruff, mypy, pytest — and stop if the tree is red
  4. commit and push `main`
  5. tag, and push that one tag on its own so the workflow fires
  6. wait for the workflow, then replace its generated notes with the CHANGELOG
     section, which is the text a reader actually wants
  7. confirm the release carries the built wheel and sdist

Without `--yes` it prints the plan and changes nothing.

    python scripts/release.py 0.7.2                      # show the plan
    python scripts/release.py 0.7.2 --yes --token-file ../.gh_token
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "hbestm/openlist-mcp-server"
API = f"https://api.github.com/repos/{REPO}"
WORKFLOW_POLL_SECONDS = 15
WORKFLOW_POLL_ATTEMPTS = 40


def run(cmd: list[str], *, token_file: Path | None = None, check: bool = True) -> str:
    """Run a command from the repository root, echoing it first.

    `token_file`, when given, is handed to git as a one-shot credential helper: the
    token never reaches the command line or a config file.
    """
    if token_file is not None:
        helper = f'!f() {{ echo username=x-access-token; echo "password=$(cat {token_file})"; }}; f'
        cmd = [cmd[0], "-c", f"credential.helper={helper}", *cmd[1:]]
    print(f"    $ {' '.join(cmd[:3])}{' …' if len(cmd) > 3 else ''}")
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-8:]
        raise SystemExit("  ✗ command failed:\n      " + "\n      ".join(tail))
    return result.stdout.strip()


def read_version() -> str:
    match = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    if match is None:
        raise SystemExit("pyproject.toml has no version")
    return match.group(1)


def as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def changelog_section(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    return match.group(1).strip("\n") if match else ""


def api(token: str, url: str, *, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.load(error)
        except Exception:  # noqa: BLE001
            return error.code, {}


def report_leftover_drafts(token: str) -> None:
    """Flag stale draft releases before adding another release to the pile.

    A draft is invisible to the public and cannot become `latest`, so it is
    harmless — with one wrinkle. A draft does not claim its tag, so GitHub parks it
    at an `untagged-<hash>` URL, where it sits in the maintainer's release list
    indefinitely and looks like something that went wrong. This project carried two
    of them (v0.2.5, v0.2.12, both May-June 2026), each a duplicate of a release
    that had already been published.
    """
    status, releases = api(token, f"{API}/releases?per_page=100")
    if status != 200 or not isinstance(releases, list):
        print("  drafts          : could not read the release list")
        return

    drafts = [release for release in releases if release.get("draft")]
    if not drafts:
        print("  drafts          : none")
        return

    print(f"  drafts          : {len(drafts)} left over — invisible to the public, safe to delete")
    for draft in drafts:
        print(
            f"      {draft['tag_name']} (id={draft['id']}, created {draft['created_at'][:10]}, "
            f"{len(draft.get('assets', []))} assets)"
        )
    print("      delete one with:")
    print(f'        curl -X DELETE -H "Authorization: Bearer $TOKEN" {API}/releases/<id>')


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("version", help="the version to release, e.g. 0.7.2")
    parser.add_argument("--yes", action="store_true", help="actually do it")
    parser.add_argument("--token-file", type=Path, help="file holding a GitHub token")
    parser.add_argument("--skip-tests", action="store_true", help="skip the gates (not advised)")
    args = parser.parse_args()

    tag = f"v{args.version}"
    current = read_version()

    print(f"  current version : {current}")
    print(f"  releasing       : {args.version}  (tag {tag})")

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise SystemExit("  ✗ version must look like MAJOR.MINOR.PATCH")
    if as_tuple(args.version) <= as_tuple(current):
        raise SystemExit(f"  ✗ {args.version} is not greater than the current {current}")

    body = changelog_section(args.version)
    if not body:
        raise SystemExit(
            f"  ✗ CHANGELOG.md has no '## [{args.version}]' section.\n"
            "    Write the entry first — the release notes come straight from it."
        )
    print(f"  changelog entry : {len(body)} characters")

    token = None
    if args.token_file is not None:
        if not args.token_file.is_file():
            raise SystemExit(f"  ✗ token file not found: {args.token_file}")
        token = args.token_file.read_text().strip()
    if token is None:
        print("  note: no --token-file, so the tag can be pushed but the release notes")
        print("        cannot be finished; git will use its own credentials.")
    else:
        report_leftover_drafts(token)

    if not args.yes:
        print("\n  Plan (nothing done yet):")
        for step in (
            f"bump pyproject.toml {current} → {args.version}",
            "regenerate documentation projections",
            "run ruff, mypy, pytest",
            "commit and push main",
            f"tag {tag} and push that tag alone (multi-tag pushes skip the workflow)",
            "wait for the release workflow",
            "replace the generated release notes with the CHANGELOG section",
            "verify the wheel and sdist were attached",
        ):
            print(f"    - {step}")
        print("\n  Re-run with --yes to proceed.")
        return 0

    print("\n  [1/8] bump pyproject.toml")
    path = ROOT / "pyproject.toml"
    path.write_text(
        re.sub(
            r'^version = "[^"]+"',
            f'version = "{args.version}"',
            path.read_text(),
            count=1,
            flags=re.M,
        ),
        encoding="utf-8",
    )

    print("  [2/8] regenerate the documentation projections")
    run([sys.executable, "scripts/render_tool_docs.py"])

    print("  [3/8] gates")
    if args.skip_tests:
        print("    skipped by --skip-tests")
    else:
        run([sys.executable, "-m", "ruff", "check", "src/", "tests/", "scripts/"])
        run([sys.executable, "-m", "ruff", "format", "src/", "tests/", "scripts/", "--check"])
        run([sys.executable, "-m", "mypy", "src/openlist_mcp/"])
        run([sys.executable, "-m", "pytest", "tests/", "-q"])

    print("  [4/8] commit and push main")
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"release: v{args.version}"])
    run(["git", "push", "origin", "main"], token_file=args.token_file)

    print(f"  [5/8] tag {tag} and push it on its own")
    run(["git", "tag", "-a", tag, "-m", f"{tag} — {body.splitlines()[0].strip('# ')}"])
    run(["git", "push", "origin", tag], token_file=args.token_file)

    print("  [6/8] wait for the release workflow")
    if token is None:
        print("    skipped: needs a token to query the workflow")
    else:
        for attempt in range(WORKFLOW_POLL_ATTEMPTS):
            time.sleep(WORKFLOW_POLL_SECONDS)
            _, runs = api(token, f"{API}/actions/workflows/release.yml/runs?per_page=5")
            run_for_tag = next(
                (r for r in runs.get("workflow_runs", []) if r.get("head_branch") == tag), None
            )
            if run_for_tag is None:
                print(f"    [{attempt}] workflow not listed yet")
                continue
            status, conclusion = run_for_tag["status"], run_for_tag.get("conclusion")
            print(f"    [{attempt}] {status} {conclusion or ''}")
            if status == "completed":
                if conclusion != "success":
                    raise SystemExit(f"  ✗ the release workflow finished as {conclusion}")
                break
        else:
            raise SystemExit("  ✗ the release workflow did not finish in time; check Actions")

        print("  [7/8] replace the generated notes with the CHANGELOG section")
        status, release = api(token, f"{API}/releases/tags/{tag}")
        if status != 200:
            raise SystemExit(f"  ✗ no release for {tag}: {release.get('message')}")
        compare = f"https://github.com/{REPO}/compare/v{current}...{tag}"
        notes = f"{body}\n\n**Full Changelog**: {compare}\n"
        status, _ = api(
            token, f"{API}/releases/{release['id']}", method="PATCH", payload={"body": notes}
        )
        print(f"    notes set from CHANGELOG ({len(notes)} characters, HTTP {status})")

        print("  [8/8] verify the built artifacts")
        _, release = api(token, f"{API}/releases/tags/{tag}")
        assets = [a["name"] for a in release.get("assets", [])]
        if not any(a.endswith(".whl") for a in assets) or not any(
            a.endswith(".tar.gz") for a in assets
        ):
            raise SystemExit(f"  ✗ expected a wheel and an sdist, found: {assets}")
        print(f"    {', '.join(assets)}")

    print(f"\n  ✅ {tag} released. Run `git log --oneline -1` if the bump needs a look.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
