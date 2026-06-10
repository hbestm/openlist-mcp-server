"""File system tools for OpenList MCP Server."""

from __future__ import annotations

import json
import posixpath

from mcp.server.fastmcp import FastMCP

from ..client import OpenListError, get_client
from . import (
    _human_size,
    _list_items,
    enforce_path_allowed,
    enforce_writable,
    normalize_names,
    validate_name,
    validate_pagination,
)




def register_fs_tools(mcp: FastMCP) -> None:
    """Register file system operation MCP tools."""

    @mcp.tool()
    async def list_files(
        path: str = "/",
        page: int = 1,
        per_page: int = 50,
        password: str = "",
    ) -> str:
        """List files and folders in a directory on OpenList.

        Args:
            path: Directory path to list. Use "/" for root. Defaults to "/".
            page: Page number for pagination. Defaults to 1.
            per_page: Number of items per page (max 200). Defaults to 50.
            password: Password if the directory is password-protected. Defaults to "".

        Returns:
            JSON string containing file list with name, size, type, modified time, etc.
        """
        enforce_path_allowed(path)
        validate_pagination(page, per_page)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/list",
            json={
                "path": path,
                "page": page,
                "per_page": per_page,
                "password": password,
            },
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def list_dirs(
        path: str = "/",
        password: str = "",
        force_root: bool = False,
    ) -> str:
        """List subdirectories under a directory.

        This is useful when an agent needs to choose a safe target directory
        without reading every file in the current path.

        Args:
            path: Directory path to list. Use "/" for root. Defaults to "/".
            password: Password if the directory is password-protected. Defaults to "".
            force_root: Ask OpenList to force listing from root when supported.

        Returns:
            JSON string containing child directory entries.
        """
        enforce_path_allowed(path)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/dirs",
            json={
                "path": path,
                "password": password,
                "force_root": force_root,
            },
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_file_info(
        path: str,
        password: str = "",
    ) -> str:
        """Get detailed information about a specific file or folder.

        Args:
            path: Full path to the file or folder.
            password: Password if the path is password-protected. Defaults to "".

        Returns:
            JSON string with file details including size, type, provider, raw_url, etc.
        """
        enforce_path_allowed(path)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/get",
            json={
                "path": path,
                "password": password,
            },
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def search_files(
        parent: str = "/",
        keywords: str = "",
        scope: int = 0,
        page: int = 1,
        per_page: int = 50,
        password: str = "",
    ) -> str:
        """Search for files and folders by keyword.

        Args:
            parent: Directory path to search in. Use "/" for root. Defaults to "/".
            keywords: Search keywords to match against file/folder names. Defaults to "".
            scope: Search scope. 0 = all types, 1 = directories only, 2 = files only. Defaults to 0.
            page: Page number for pagination. Defaults to 1.
            per_page: Number of items per page. Defaults to 50.
            password: Password if the directory is password-protected. Defaults to "".

        Returns:
            JSON string containing matching files and folders.
        """
        enforce_path_allowed(parent)
        validate_pagination(page, per_page)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/search",
            json={
                "parent": parent,
                "keywords": keywords,
                "scope": scope,
                "page": page,
                "per_page": per_page,
                "password": password,
            },
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def create_folder(
        path: str,
    ) -> str:
        """Create a new folder (directory) on OpenList.

        Args:
            path: Full path of the new folder to create (e.g. "/photos/2024").

        Returns:
            Success or error message.
        """
        enforce_path_allowed(path)
        enforce_writable("create_folder")
        client = await get_client()
        await client.request(
            "POST",
            "fs/mkdir",
            json={"path": path},
        )
        return f"Folder created successfully: {path}"

    @mcp.tool()
    async def rename(
        path: str,
        name: str,
    ) -> str:
        """Rename a file or folder.

        Args:
            path: Full path to the file or folder to rename.
            name: New name (not full path, just the new file/folder name).

        Returns:
            Success or error message.
        """
        enforce_path_allowed(path)
        enforce_writable("rename")
        validate_name(name)
        client = await get_client()
        await client.request(
            "POST",
            "fs/rename",
            json={"path": path, "name": name},
        )
        return f"Renamed successfully: {path} -> {name}"

    @mcp.tool()
    async def batch_rename(
        src_dir: str,
        rename_objects: list[dict[str, str]],
    ) -> str:
        """Rename multiple files or folders in the same directory.

        Args:
            src_dir: Directory containing the files/folders to rename.
            rename_objects: List of objects with src_name and new_name fields.

        Returns:
            Success message or OpenList task/result info.
        """
        enforce_path_allowed(src_dir)
        enforce_writable("batch_rename")
        if not rename_objects:
            return "No rename objects specified."

        normalized_objects = []
        for item in rename_objects:
            src_name = item.get("src_name", "").strip()
            new_name = item.get("new_name", "").strip()
            validate_name(src_name)
            validate_name(new_name)
            normalized_objects.append({"src_name": src_name, "new_name": new_name})

        client = await get_client()
        data = await client.request(
            "POST",
            "fs/batch_rename",
            json={
                "src_dir": src_dir,
                "rename_objects": normalized_objects,
            },
        )
        if data is not None and data != {}:
            return f"Batch rename result: {json.dumps(data, ensure_ascii=False)}"
        return f"Batch renamed successfully in {src_dir}: {normalized_objects}"

    @mcp.tool()
    async def regex_rename(
        src_dir: str,
        src_name_regex: str,
        new_name_regex: str,
    ) -> str:
        """Rename files in a directory using regular expression substitution.

        All files in src_dir whose names match src_name_regex will be renamed
        by replacing the matched portion with new_name_regex.

        The replacement uses Go regex syntax — use $1, $2 for capture groups
        (NOT \\1 or \\g<1> like in Python/JS).

        Examples:
          - src_name_regex="(.*)\\.html"  new_name_regex="$1.htm"
            Changes .html extension to .htm for all HTML files.
          - src_name_regex="^report_"     new_name_regex="draft_"
            Prefixes "draft_" to files starting with "report_".
          - src_name_regex="(\\d{4})-(\\d{2})-(\\d{2})_(.*)"
            new_name_regex="$3/$1/$2_$4"
            Rearranges date-prefixed filenames.

        Args:
            src_dir: Directory containing the files to rename.
            src_name_regex: Regex pattern to match source filenames.
            new_name_regex: Replacement pattern. Use $1, $2 to reference
                           capture groups (Go regex syntax).

        Returns:
            Success or error message with operation result.
        """
        enforce_writable("regex_rename")
        enforce_path_allowed(src_dir)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/regex_rename",
            json={
                "src_dir": src_dir,
                "src_name_regex": src_name_regex,
                "new_name_regex": new_name_regex,
            },
        )
        if data is not None and data != {}:
            return f"Regex rename result: {json.dumps(data, ensure_ascii=False)}"
        return f"Regex rename completed in {src_dir}: {src_name_regex} -> {new_name_regex}"

    @mcp.tool()
    async def copy(
        src_dir: str,
        dst_dir: str,
        names: list[str] | str,
    ) -> str:
        """Copy files or folders to another directory.

        Args:
            src_dir: Source directory path containing the items to copy.
            dst_dir: Destination directory path.
            names: List of file/folder names or comma-separated string to copy (e.g. ["file1.txt", "file2.pdf"] or "file1.txt,file2.pdf").

        Returns:
            Success or error message with task info if processed asynchronously.
        """
        enforce_writable("copy")
        enforce_path_allowed(src_dir)
        enforce_path_allowed(dst_dir)
        client = await get_client()
        name_list = normalize_names(names)

        if not name_list:
            return "No files specified to copy. Please provide at least one file name."
        data = await client.request(
            "POST",
            "fs/copy",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": name_list,
            },
        )
        if data is not None and data != {}:
            return f"Copy task created: {json.dumps(data, ensure_ascii=False)}"
        return f"Copied successfully: {name_list} -> {dst_dir}"

    @mcp.tool()
    async def move(
        src_dir: str,
        dst_dir: str,
        names: list[str] | str,
    ) -> str:
        """Move files or folders to another directory.

        Args:
            src_dir: Source directory path containing the items to move.
            dst_dir: Destination directory path.
            names: List of file/folder names or comma-separated string to move (e.g. ["file1.txt", "file2.pdf"] or "file1.txt,file2.pdf").

        Returns:
            Success or error message with task info if processed asynchronously.
        """
        enforce_writable("move")
        enforce_path_allowed(src_dir)
        enforce_path_allowed(dst_dir)
        client = await get_client()
        name_list = normalize_names(names)

        if not name_list:
            return "No files specified to move. Please provide at least one file name."
        data = await client.request(
            "POST",
            "fs/move",
            json={
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": name_list,
            },
        )
        if data is not None and data != {}:
            return f"Move task created: {json.dumps(data, ensure_ascii=False)}"
        return f"Moved successfully: {name_list} -> {dst_dir}"

    @mcp.tool()
    async def remove(
        directory: str,
        names: list[str] | str,
        confirm: bool = False,
    ) -> str:
        """Delete files or folders.

        Args:
            directory: Directory path containing the items to delete.
            names: List of file/folder names or comma-separated string to delete (e.g. ["file1.txt", "old_folder"] or "file1.txt,old_folder").
            confirm: Must be true to actually delete items. Defaults to false.

        Returns:
            Success or confirmation-required message.
        """
        enforce_path_allowed(directory)
        if not confirm:
            return "⚠️ Deletion not performed. Re-run with confirm=true to delete these items."
        enforce_writable("remove")
        client = await get_client()
        name_list = normalize_names(names)

        if not name_list:
            return "No files specified to delete. Please provide at least one file name."
        await client.request(
            "POST",
            "fs/remove",
            json={"dir": directory, "names": name_list},
        )
        return f"Deleted successfully: {name_list} from {directory}"

    @mcp.tool()
    async def remove_empty_dirs(
        src_dir: str,
        confirm: bool = False,
    ) -> str:
        """Recursively remove empty directories under the given path.

        Deletes directories that contain no files (only empty subdirectories
        are also removed). Useful for cleanup after moving or deleting files.

        Args:
            src_dir: Directory path to scan for empty subdirectories.
            confirm: Must be true to actually delete. Defaults to false.

        Returns:
            Success message or confirmation-required message.
        """
        if not confirm:
            return (
                "Empty directory removal not performed. "
                "⚠️ Re-run with confirm=true to remove empty directories."
            )
        enforce_writable("remove_empty_dirs")
        enforce_path_allowed(src_dir)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/remove_empty_directory",
            json={"src_dir": src_dir},
        )
        if data is not None and data != {}:
            return f"Empty directory removal result: {json.dumps(data, ensure_ascii=False)}"
        return f"Empty directories removed successfully under: {src_dir}"

    @mcp.tool()
    async def recursive_move(
        src_dir: str,
        dst_dir: str,
    ) -> str:
        """Recursively move an entire directory tree to a new location.

        Unlike the move tool, this does not require listing individual file names.
        The entire source directory and all its contents are moved together.

        Args:
            src_dir: Source directory path to move.
            dst_dir: Destination directory path.

        Returns:
            Success message or task info.
        """
        enforce_path_allowed(src_dir)
        enforce_path_allowed(dst_dir)
        enforce_writable("recursive_move")
        client = await get_client()

        # Try the native API first (OpenList v4.3+)
        try:
            data = await client.request(
                "POST",
                "fs/recursive_move",
                json={"src_dir": src_dir, "dst_dir": dst_dir},
            )
            if data is not None and data != {}:
                return f"Recursive move task created: {json.dumps(data, ensure_ascii=False)}"
            return f"Recursive move completed: {src_dir} -> {dst_dir}"
        except OpenListError as exc:
            message = exc.message.lower()
            if not any(
                marker in message
                for marker in ("not found", "unsupported", "method not allowed", "recursive_move")
            ):
                raise

        # Fallback: OpenList v4.2.x doesn't support fs/recursive_move.
        # Use rename (same parent) or move+rename (different parents).
        src_dir_clean = src_dir.rstrip("/")
        dst_dir_clean = dst_dir.rstrip("/")
        src_name = posixpath.basename(src_dir_clean)
        src_parent = posixpath.dirname(src_dir_clean) or "/"
        dst_parent = posixpath.dirname(dst_dir_clean) or "/"
        dst_name = posixpath.basename(dst_dir_clean)
        validate_name(src_name)
        validate_name(dst_name)

        if src_parent == dst_parent:
            # Same parent directory — just rename
            await client.request(
                "POST",
                "fs/rename",
                json={"path": src_dir_clean, "name": dst_name},
            )
            return f"Recursive move completed (rename): {src_dir} -> {dst_dir}"
        else:
            # Different parents — move then rename
            await client.request(
                "POST",
                "fs/move",
                json={
                    "src_dir": src_parent,
                    "dst_dir": dst_parent,
                    "names": [src_name],
                },
            )
            if src_name != dst_name:
                moved_path = (
                    f"{dst_parent.rstrip('/')}/{src_name}" if dst_parent != "/" else f"/{src_name}"
                )
                await client.request(
                    "POST",
                    "fs/rename",
                    json={"path": moved_path, "name": dst_name},
                )
            return f"Recursive move completed (move+rename): {src_dir} -> {dst_dir}"

    @mcp.tool()
    async def tree(
        path: str = "/",
        max_depth: int = 3,
        password: str = "",
    ) -> str:
        """Build a recursive directory tree for the given path.

        Returns an indented tree structure showing nested files and folders,
        useful for understanding the overall layout of a directory.

        Args:
            path: Root directory to start the tree from. Defaults to "/".
            max_depth: Maximum nesting depth (1 = current level only). Defaults to 3.
            password: Password if the path is password-protected.

        Returns:
            A formatted string showing the directory tree.
        """
        client = await get_client()

        lines = []
        seen = set()

        async def _walk(dir_path: str, depth: int = 0, prefix: str = "") -> None:
            if depth > max_depth:
                return
            if dir_path in seen:
                lines.append(f"{prefix}  (...symlink/loop)")
                return
            seen.add(dir_path)

            try:
                items = await _list_items(client, dir_path, password)
                if not items:
                    lines.append(f"{prefix}  (error listing)")
                    return
            except Exception:
                lines.append(f"{prefix}  (error listing)")
                return

            # Separate dirs and files, sort alphabetically
            dirs = sorted(
                [i for i in items if i.get("type") in (1, "dir", "folder")], key=lambda x: x["name"]
            )
            files = sorted([i for i in items if i.get("type") not in (1, "dir", "folder")], key=lambda x: x["name"])
            entries = dirs + files

            for idx, entry in enumerate(entries):
                is_last = idx == len(entries) - 1
                connector = "└── " if is_last else "├── "
                sub_prefix = prefix + ("    " if is_last else "│   ")
                name = entry["name"]
                size = entry.get("size", 0)
                typ = entry.get("type", "")
                is_dir = typ in (1, "dir", "folder")

                if is_dir:
                    lines.append(f"{prefix}{connector}📁 {name}/")
                    await _walk(f"{dir_path.rstrip('/')}/{name}", depth + 1, sub_prefix)
                else:
                    size_str = f" ({size} B)" if size else ""
                    lines.append(f"{prefix}{connector}📄 {name}{size_str}")

        # Root display
        display_path = path if path != "/" else "/ (root)"
        lines.append(f"📁 {display_path}")
        await _walk(path, 1, "")

        return "\n".join(lines)

    @mcp.tool()
    async def disk_usage(
        path: str = "/",
        password: str = "",
    ) -> str:
        """Show disk usage summary for a directory.

        Recursively calculates total size and item count, broken down by
        subdirectory and grouped by file type. Useful for understanding
        what's consuming space on the server.

        Args:
            path: Directory to analyze. Defaults to "/".
            password: Password if the path is password-protected.

        Returns:
            JSON string with size breakdown by directory and file type.
        """
        client = await get_client()

        total_size = 0
        total_files = 0
        dir_sizes: dict[str, int] = {}
        type_sizes: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        seen = set()

        async def _walk(dir_path: str, depth: int = 0) -> None:
            nonlocal total_size, total_files
            if depth > 5:
                return
            if dir_path in seen:
                return
            seen.add(dir_path)

            items = await _list_items(client, dir_path, password)
            if not items:
                return

            for item in items:
                name = item["name"]
                size = item.get("size", 0) or 0
                typ = item.get("type", "")
                is_dir = typ in (1, "dir", "folder")
                ext = ""

                if is_dir:
                    sub_path = f"{dir_path.rstrip('/')}/{name}"
                    sub_start = total_size
                    await _walk(sub_path, depth + 1)
                    sub_size = total_size - sub_start
                    dir_sizes[sub_path] = sub_size
                else:
                    total_files += 1
                    total_size += size
                    # Get extension
                    ext = name.rsplit(".", 1)[1].lower() if "." in name else "(no ext)"
                    type_sizes[ext] = type_sizes.get(ext, 0) + size
                    type_counts[ext] = type_counts.get(ext, 0) + 1

        await _walk(path)

        # Build result
        # Top 10 directories by size
        top_dirs = sorted(dir_sizes.items(), key=lambda x: -x[1])[:10]
        # File types by size
        top_types = sorted(type_sizes.items(), key=lambda x: -x[1])

        result = {
            "path": path,
            "total_size": total_size,
            "total_size_human": _human_size(total_size),
            "total_files": total_files,
            "top_directories": [
                {"path": p, "size": s, "size_human": _human_size(s)} for p, s in top_dirs
            ],
            "by_file_type": [
                {
                    "extension": ext,
                    "count": type_counts.get(ext, 0),
                    "size": s,
                    "size_human": _human_size(s),
                }
                for ext, s in top_types
            ],
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def mirror(
        src_dir: str,
        dst_dir: str,
        mode: str = "push",
        dry_run: bool = True,
        password: str = "",
    ) -> str:
        """Synchronize files from a source directory to a destination directory.

        Walks both directories recursively, compares the file trees, and copies
        files that exist in source but are missing from destination. The source
        directory itself is never modified.

        Args:
            src_dir: Source directory path. Contents are read-only.
            dst_dir: Destination directory path. New files and folders are
                     created here to match the source.
            mode: "push" — only copy missing files from src to dst (default).
                  "pull" — only copy files from dst to src.
                  "mirror" — push + delete files in dst that don't exist in src.
            dry_run: When true (default), only list what would be done without
                     actually copying. Set to false to execute.
            password: Password if the path is password-protected.

        Returns:
            Report of files copied, skipped, and deleted.
        """
        enforce_path_allowed(src_dir)
        enforce_path_allowed(dst_dir)
        if mode not in ("push", "pull", "mirror"):
            return f"Invalid mode '{mode}'. Must be 'push', 'pull', or 'mirror'."
        if mode in ("push", "mirror"):
            enforce_writable(f"mirror ({mode} to dst)")
        if mode == "pull":
            enforce_writable("mirror (pull from dst)")

        client = await get_client()

        async def _list_tree(path: str) -> dict[str, dict]:
            """Recursively list files, returning {relative_path: info}."""
            result: dict[str, dict] = {}
            seen = set()

            async def _walk(dir_path: str, rel_prefix: str = "") -> None:
                if dir_path in seen:
                    return
                seen.add(dir_path)
                try:
                    data = await client.request(
                        "POST",
                        "fs/list",
                        json={"path": dir_path, "page": 1, "per_page": 200, "password": password},
                    )
                except Exception:
                    return
                items = data.get("content", data.get("value", []))
                if not isinstance(items, list):
                    items = []
                for item in items:
                    name = item["name"]
                    typ = item.get("type", "")
                    is_dir = typ in (1, "dir", "folder")
                    rel = f"{rel_prefix}{name}" + ("/" if is_dir else "")
                    if is_dir:
                        result[rel] = {"type": "dir", "name": name}
                        await _walk(f"{dir_path.rstrip('/')}/{name}", f"{rel_prefix}{name}/")
                    else:
                        result[rel] = {
                            "type": "file",
                            "name": name,
                            "size": item.get("size", 0),
                        }

            await _walk(path)
            return result

        src_files = await _list_tree(src_dir)
        dst_files = await _list_tree(dst_dir)

        # In pull mode, swap roles: treat dst as source and src as destination
        if mode == "pull":
            src_files, dst_files = dst_files, src_files
            copy_src_dir, copy_dst_dir = dst_dir, src_dir
        else:
            copy_src_dir, copy_dst_dir = src_dir, dst_dir

        to_copy = []
        to_delete = []

        for rel, info in src_files.items():
            if info["type"] == "file" and rel not in dst_files:
                to_copy.append(rel)
            if info["type"] == "dir" and rel not in dst_files:
                to_copy.append(rel)

        if mode == "mirror":
            for rel in dst_files:
                if rel not in src_files:
                    to_delete.append(rel)
        to_copy.sort(key=lambda x: (0, x) if x.endswith("/") else (1, x))

        report = {
            "src_dir": src_dir,
            "dst_dir": dst_dir,
            "mode": mode,
            "dry_run": dry_run,
            "src_files_total": len(src_files),
            "dst_files_total": len(dst_files),
            "files_to_copy": len(to_copy),
            "files_to_delete": len(to_delete),
            "copy_list": to_copy[:20],
            "delete_list": to_delete[:20],
            "note": "truncated at 20 items" if len(to_copy) > 20 or len(to_delete) > 20 else "",
        }

        if dry_run:
            return json.dumps(report, indent=2, ensure_ascii=False)

        # Execute
        copied = 0
        deleted = 0
        errors = []

        for rel in to_copy:
            try:
                src_path = f"{copy_src_dir.rstrip('/')}/{rel}"
                if rel.endswith("/"):
                    # Create directory
                    dst_path = f"{copy_dst_dir.rstrip('/')}/{rel.rstrip('/')}"
                    await client.request("POST", "fs/mkdir", json={"path": dst_path})
                else:
                    # Copy file
                    parent = posixpath.dirname(rel.rstrip("/"))
                    dst_parent = f"{copy_dst_dir.rstrip('/')}/{parent}" if parent else copy_dst_dir
                    file_name = posixpath.basename(rel)
                    await client.request(
                        "POST",
                        "fs/copy",
                        json={
                            "src_dir": posixpath.dirname(src_path),
                            "dst_dir": dst_parent,
                            "names": [file_name],
                        },
                    )
                copied += 1
            except Exception as e:
                errors.append(f"copy {rel}: {e}")

        for rel in to_delete:
            try:
                dir_path = posixpath.dirname(f"{copy_dst_dir.rstrip('/')}/{rel.rstrip('/')}")
                name = posixpath.basename(rel.rstrip("/"))
                await client.request(
                    "POST",
                    "fs/remove",
                    json={"dir": dir_path, "names": [name]},
                )
                deleted += 1
            except Exception as e:
                errors.append(f"delete {rel}: {e}")

        report["copied"] = copied
        report["deleted"] = deleted
        report["errors"] = errors
        return json.dumps(report, indent=2, ensure_ascii=False)
