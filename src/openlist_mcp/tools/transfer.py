"""File transfer tools for OpenList MCP Server."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

from .._compat import FastMCP
from ..client import OpenListClient, OpenListError, get_client
from . import enforce_path_allowed, enforce_writable, validate_name

# Maximum base64 content length for upload_file (~75MB raw, ~100MB base64).
# For larger files, use upload_local_file which streams from disk.
MAX_BASE64_UPLOAD_BYTES = 104_857_600  # 100 MB base64 string length

# Resumable multipart uploads (OpenList post-v4.2.5 master). Chunks are
# clamped by the server to [1 MiB, admin multipart_chunk_size ceiling].
MIN_MULTIPART_CHUNK = 1024 * 1024  # 1 MiB


def _received_chunk_indexes(received_ranges: list | None) -> set[int]:
    """Expand the server's received chunk ranges into a set of chunk indexes.

    The OpenList session snapshot reports ``received`` as inclusive [start, end]
    chunk-index ranges (e.g. [[0, 2], [5, 5]]).
    """
    indexes: set[int] = set()
    for start, end in received_ranges or []:
        try:
            indexes.update(range(int(start), int(end) + 1))
        except (TypeError, ValueError):
            continue
    return indexes


def _md5_hexdigest(data: bytes) -> str:
    """MD5 of an in-memory upload payload (used as the resume identity proof)."""
    return hashlib.md5(data).hexdigest()


def _md5_hexdigest_file(path: Path) -> str:
    """Streaming MD5 of a local file (used as the resume identity proof)."""
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _has_task_result(data: dict | None) -> bool:
    """True when an upload response carries real task data (not a null body).

    OpenList returns ``{"value": null}`` for synchronous (non-task) uploads —
    that is a success without task info, not "task created".
    """
    if not data:
        return False
    if isinstance(data, dict) and data.get("value") is None:
        return False
    return data != {}


def _allowed_upload_roots() -> list[Path]:
    roots = os.environ.get("OPENLIST_LOCAL_UPLOAD_ROOTS", "").strip()
    if not roots:
        return []
    return [Path(root).expanduser().resolve() for root in roots.split(os.pathsep) if root.strip()]


def _is_allowed_local_path(file_path: Path) -> bool:
    roots = _allowed_upload_roots()
    if not roots:
        return False
    resolved = file_path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


async def _iter_file_chunks(file_path: Path, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    with file_path.open("rb") as file_obj:
        while chunk := file_obj.read(chunk_size):
            yield chunk
            await asyncio.sleep(0)


async def _run_multipart_upload(
    client: OpenListClient,
    *,
    target_path: str,
    total_size: int,
    chunk_size: int,
    overwrite: bool,
    data: bytes | None = None,
    file_path: Path | None = None,
) -> str:
    """Drive an OpenList multipart session: init → chunks → complete.

    Chunking happens here with the effective (server-clamped) chunk size, so
    the client and server always agree on chunk boundaries. Re-invoking with
    the same target path/size resumes an in-progress session; already-received
    chunks are skipped. Either ``data`` (in-memory) or ``file_path``
    (streamed from disk) must be provided.
    """
    effective_chunk = max(MIN_MULTIPART_CHUNK, int(chunk_size))

    # OpenList (post-v4.2.5) only lets a client resume an in-progress session
    # when it can prove the new upload is the same file: it requires a matching
    # hash (X-File-Md5 etc.). Without one, the server treats the retry as a new
    # file, terminates the old session and re-uploads everything. Always send
    # the MD5 of the payload so interrupted uploads genuinely resume.
    file_md5: str | None = None
    if data is not None:
        file_md5 = _md5_hexdigest(data)
    elif file_path is not None:
        file_md5 = _md5_hexdigest_file(file_path)

    init_data = await client.multipart_init(
        file_path=target_path,
        file_size=total_size,
        chunk_size=effective_chunk,
        overwrite=overwrite,
        file_md5=file_md5,
    )
    upload_id = init_data.get("upload_id", "")
    if not upload_id:
        return json.dumps(
            {"ok": False, "error": "Multipart init returned no upload_id.", "init": init_data},
            indent=2,
            ensure_ascii=False,
        )

    # When resuming, skip chunks the server already received.
    skip_indexes: set[int] = set()
    if init_data.get("resumed"):
        with contextlib.suppress(Exception):
            status = await client.multipart_status(upload_id=upload_id)
            if status:
                skip_indexes = _received_chunk_indexes(status.get("received"))

    # Slice by the server's actual session chunk size (returned by init) so we
    # agree with the session even when the server clamped or resumed an older
    # session with a different chunk size.
    server_chunk = init_data.get("chunk_size")
    slice_chunk = int(server_chunk) if server_chunk and int(server_chunk) > 0 else effective_chunk
    total_chunks = (total_size + slice_chunk - 1) // slice_chunk
    sent = 0
    errors: list[str] = []
    file_obj = file_path.open("rb") if file_path else None
    try:
        for index in range(total_chunks):
            if index in skip_indexes:
                sent += 1
                continue
            if file_obj is not None:
                file_obj.seek(index * slice_chunk)
                chunk = file_obj.read(min(slice_chunk, total_size - index * slice_chunk))
            else:
                start = index * slice_chunk
                chunk = data[start : start + slice_chunk]  # type: ignore[index]
            try:
                await client.multipart_chunk(upload_id, index, chunk)
                sent += 1
            except OpenListError as exc:
                errors.append(f"chunk {index}: {exc.message}")
                break
    finally:
        if file_obj is not None:
            file_obj.close()

    if errors:
        status = {}
        with contextlib.suppress(Exception):
            status = await client.multipart_status(upload_id=upload_id)
        return json.dumps(
            {
                "ok": False,
                "upload_id": upload_id,
                "error": errors,
                "chunks_sent": sent,
                "total_chunks": total_chunks,
                "status": status,
                "resume_hint": (
                    "Re-run the same multipart upload with the same path/file "
                    "name/size to resume, or call multipart_abort_upload."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    complete = await client.multipart_complete(upload_id)
    return json.dumps(
        {
            "ok": True,
            "upload_id": upload_id,
            "chunks_sent": sent,
            "total_chunks": total_chunks,
            "complete": complete,
        },
        indent=2,
        ensure_ascii=False,
    )


def register_transfer_tools(mcp: FastMCP) -> None:
    """Register file upload/download MCP tools."""

    @mcp.tool()
    async def get_download_url(
        path: str,
        password: str = "",
    ) -> str:
        """Get the download URL for a file on OpenList.

        This returns the direct download link (or proxy link) for a file.
        The URL may include a time-limited signature for security.

        Args:
            path: Full path to the file.
            password: Password if the path is password-protected. Defaults to "".

        Returns:
            The download URL for the file, or file info with raw_url.
        """
        enforce_path_allowed(path)
        client = await get_client()
        data = await client.request(
            "POST",
            "fs/get",
            json={"path": path, "password": password},
        )
        raw_url = data.get("raw_url", "")
        if raw_url:
            return json.dumps(
                {"download_url": raw_url, "path": path},
                indent=2,
                ensure_ascii=False,
            )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def upload_file(
        path: str,
        file_name: str,
        file_content_base64: str,
        as_task: bool = True,
    ) -> str:
        """Upload a file to OpenList from base64-encoded content.

        Args:
            path: Target directory path on OpenList (e.g. "/documents").
            file_name: Name for the uploaded file (e.g. "report.pdf").
            file_content_base64: Base64-encoded file content.
            as_task: Process as async task for large files. Defaults to True.

        Returns:
            Success message or task ID for async uploads.
        """
        enforce_path_allowed(path)
        enforce_writable("upload_file")
        validate_name(file_name)

        if len(file_content_base64) > MAX_BASE64_UPLOAD_BYTES:
            raw_mb = len(file_content_base64) * 3 // 4 // 1024 // 1024
            return (
                f"File too large ({raw_mb} MB estimated raw). "
                f"Maximum base64 upload is {MAX_BASE64_UPLOAD_BYTES // 1024 // 1024} MB. "
                "For larger files, use upload_local_file which streams from disk."
            )

        client = await get_client()
        try:
            file_bytes = base64.b64decode(file_content_base64)
        except (ValueError, binascii.Error) as e:
            return f"Failed to decode base64 content: {e}"

        data = await client.upload(
            path=path,
            file_content=file_bytes,
            file_name=file_name,
            as_task=as_task,
        )
        if _has_task_result(data):
            return f"Upload task created: {json.dumps(data, ensure_ascii=False)}"
        return f"File uploaded successfully: {path}/{file_name}"

    @mcp.tool()
    async def upload_local_file(
        local_path: str,
        remote_dir: str,
        remote_name: str = "",
        as_task: bool = True,
    ) -> str:
        """Upload a local file that the MCP server process can access.

        Use this when the agent and MCP server run on the same machine, or when the
        MCP server can read the provided file path. Set OPENLIST_LOCAL_UPLOAD_ROOTS
        to restrict readable upload paths (os.pathsep-separated). For generic MCP
        clients that cannot expose local files to the server, use upload_file with
        base64 content.

        Args:
            local_path: Local filesystem path readable by the MCP server process.
            remote_dir: Target directory path on OpenList (e.g. "/documents").
            remote_name: Optional remote filename. Defaults to the local filename.
            as_task: Process as async task for large files. Defaults to True.

        Returns:
            Success message or task ID for async uploads.
        """
        enforce_path_allowed(remote_dir)
        enforce_writable("upload_local_file")
        file_path = Path(local_path).expanduser()
        if not file_path.is_file():
            return f"Local file not found or not a regular file: {local_path}"
        if not _is_allowed_local_path(file_path):
            return (
                "Local file upload is not allowed for this path. "
                "Set OPENLIST_LOCAL_UPLOAD_ROOTS to include an allowed parent directory."
            )

        final_name = remote_name.strip() or file_path.name
        try:
            validate_name(final_name)
        except ValueError as exc:
            return f"remote_name must be a filename only, not a path: {exc}"

        client = await get_client()
        data = await client.upload(
            path=remote_dir,
            file_content=_iter_file_chunks(file_path),
            file_name=final_name,
            as_task=as_task,
        )
        if _has_task_result(data):
            return f"Upload task created: {json.dumps(data, ensure_ascii=False)}"
        return f"File uploaded successfully: {remote_dir}/{final_name}"

    @mcp.tool()
    async def upload_file_multipart(
        path: str,
        file_name: str,
        file_content_base64: str,
        chunk_size: int = 8 * 1024 * 1024,
        overwrite: bool = True,
    ) -> str:
        """Upload a file using the resumable multipart upload API.

        Larger and more robust than upload_file: content is sent in chunks
        that survive network interruptions, and re-invoking this tool with the
        same path/name/size resumes the session instead of starting over.
        Requires an OpenList build with the multipart API (master after
        v4.2.5) and the ``multipart_enabled`` admin setting enabled.

        For very large files prefer multipart_upload_local_file, which streams
        from disk without loading the whole file into memory.

        Args:
            path: Target directory path on OpenList (e.g. "/documents").
            file_name: Name for the uploaded file (e.g. "report.iso").
            file_content_base64: Base64-encoded file content.
            chunk_size: Chunk size in bytes (min 1 MiB, clamped by the server).
            overwrite: Whether to overwrite an existing file. Defaults to true.

        Returns:
            JSON string with the final session snapshot on success, or the
            upload_id + error/status to resume or abort on failure.
        """
        enforce_path_allowed(path)
        enforce_writable("upload_file_multipart")
        validate_name(file_name)

        try:
            file_bytes = base64.b64decode(file_content_base64, validate=True)
        except (ValueError, binascii.Error):
            return json.dumps(
                {"ok": False, "error": "Failed to decode base64 content."},
                ensure_ascii=False,
            )
        if not file_bytes:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "Empty files are not supported by the multipart API; "
                        "use upload_file for empty content."
                    ),
                },
                ensure_ascii=False,
            )

        client = await get_client()
        target = f"{path.rstrip('/')}/{file_name}" if path != "/" else f"/{file_name}"
        return await _run_multipart_upload(
            client,
            target_path=target,
            total_size=len(file_bytes),
            chunk_size=chunk_size,
            overwrite=overwrite,
            data=file_bytes,
        )

    @mcp.tool()
    async def multipart_upload_local_file(
        local_path: str,
        remote_dir: str,
        remote_name: str = "",
        chunk_size: int = 8 * 1024 * 1024,
        overwrite: bool = True,
    ) -> str:
        """Upload a local file via the resumable multipart API, streaming from disk.

        Does not load the file into memory, so arbitrarily large local files
        can be uploaded. Gated by OPENLIST_LOCAL_UPLOAD_ROOTS like
        upload_local_file. Requires an OpenList build with the multipart API
        (master after v4.2.5) and the ``multipart_enabled`` setting enabled.

        Args:
            local_path: Local filesystem path readable by the MCP server.
            remote_dir: Target directory path on OpenList (e.g. "/documents").
            remote_name: Optional remote filename. Defaults to the local filename.
            chunk_size: Chunk size in bytes (min 1 MiB, clamped by the server).
            overwrite: Whether to overwrite an existing file. Defaults to true.

        Returns:
            JSON string with the final session snapshot on success, or the
            upload_id + error/status to resume or abort on failure.
        """
        enforce_path_allowed(remote_dir)
        enforce_writable("multipart_upload_local_file")
        file_path = Path(local_path).expanduser()
        if not file_path.is_file():
            return json.dumps(
                {"ok": False, "error": f"Local file not found or not a regular file: {local_path}"},
                ensure_ascii=False,
            )
        if not _is_allowed_local_path(file_path):
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "Local file upload is not allowed for this path. "
                        "Set OPENLIST_LOCAL_UPLOAD_ROOTS to include an allowed parent directory."
                    ),
                },
                ensure_ascii=False,
            )
        final_name = remote_name.strip() or file_path.name
        try:
            validate_name(final_name)
        except ValueError as exc:
            return json.dumps(
                {"ok": False, "error": f"remote_name must be a filename only, not a path: {exc}"},
                ensure_ascii=False,
            )

        total_size = file_path.stat().st_size
        if total_size == 0:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "Empty files are not supported by the multipart API; "
                        "use upload_local_file for empty content."
                    ),
                },
                ensure_ascii=False,
            )

        client = await get_client()
        target = f"{remote_dir.rstrip('/')}/{final_name}" if remote_dir != "/" else f"/{final_name}"
        return await _run_multipart_upload(
            client,
            target_path=target,
            total_size=total_size,
            chunk_size=chunk_size,
            overwrite=overwrite,
            file_path=file_path,
        )

    @mcp.tool()
    async def multipart_upload_status(
        upload_id: str = "",
        path: str = "",
        file_size: int = 0,
    ) -> str:
        """Query a multipart upload session's progress.

        Args:
            upload_id: The session upload_id returned by upload_file_multipart
                       or multipart_upload_local_file.
            path: Alternative lookup: full target path on OpenList.
            file_size: Required together with path for the path-based lookup.

        Returns:
            JSON string with the session snapshot (received chunks, progress).
        """
        if not upload_id.strip() and not (path.strip() and file_size > 0):
            raise ValueError("multipart_upload_status requires upload_id, or path and file_size")
        client = await get_client()
        data = await client.multipart_status(
            upload_id=upload_id.strip(), path=path.strip(), file_size=file_size
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def multipart_abort_upload(upload_id: str, confirm: bool = False) -> str:
        """Abort a multipart upload session and discard its chunks.

        Args:
            upload_id: The session upload_id to abort.
            confirm: Must be true to actually abort. Defaults to false.

        Returns:
            Success or confirmation-required message.
        """
        if not confirm:
            return (
                "⚠️ Multipart session abort not performed. "
                "Re-run with confirm=true to abort the upload."
            )
        enforce_writable("multipart_abort_upload")
        if not upload_id.strip():
            return "upload_id must not be empty."
        client = await get_client()
        await client.multipart_abort(upload_id.strip())
        return f"Multipart upload aborted: {upload_id}"

    @mcp.tool()
    async def get_direct_upload_info(
        path: str,
        file_name: str,
        file_size: int,
        tool: str = "",
    ) -> str:
        """Get client-side direct upload credentials for a storage backend.

        Some storage drivers (S3, etc.) support uploading directly from the
        client without proxying through the OpenList server. This returns the
        upload endpoint and credentials when the driver supports it, or null
        upload_info otherwise.

        Args:
            path: Target directory path on OpenList (e.g. "/documents").
            file_name: Name of the file to upload.
            file_size: Size of the file in bytes.
            tool: Optional upload tool hint forwarded to the storage driver.

        Returns:
            JSON string with direct upload info.
        """
        enforce_path_allowed(path)
        enforce_writable("get_direct_upload_info")
        validate_name(file_name)
        if file_size <= 0:
            return json.dumps(
                {"ok": False, "error": "file_size must be a positive integer."},
                ensure_ascii=False,
            )
        client = await get_client()
        body: dict = {"path": path, "file_name": file_name, "file_size": file_size}
        if tool:
            body["tool"] = tool
        data = await client.request("POST", "fs/get_direct_upload_info", json=body)
        return json.dumps(data, indent=2, ensure_ascii=False)
