"""Behavior tests for transfer MCP tools."""

import json

import pytest


@pytest.mark.asyncio
async def test_upload_file_validates_file_name(transfer_tools) -> None:
    tools, client = transfer_tools

    with pytest.raises(ValueError, match="path separators"):
        await tools["upload_file"]("/docs", "bad/name.txt", "aGVsbG8=")

    assert client.uploads == []


@pytest.mark.asyncio
async def test_upload_file_sends_decoded_content(transfer_tools) -> None:
    tools, client = transfer_tools

    result = await tools["upload_file"]("/docs", "note.txt", "aGVsbG8=", as_task=False)

    assert result == "File uploaded successfully: /docs/note.txt"
    assert client.uploads == [
        {
            "path": "/docs",
            "file_content": b"hello",
            "file_name": "note.txt",
            "as_task": False,
        }
    ]


@pytest.mark.asyncio
async def test_upload_file_null_result_is_reported_as_success(transfer_tools, monkeypatch) -> None:
    """OpenList returns {'value': null} for sync uploads — that is success, not a task."""

    class NullUploadClient:
        async def upload(self, **kwargs):
            return {"value": None}

    async def fake_get_client():
        return NullUploadClient()

    monkeypatch.setattr("openlist_mcp.tools.transfer.get_client", fake_get_client)

    result = await transfer_tools[0]["upload_file"]("/docs", "note.txt", "aGVsbG8=", as_task=False)

    assert result == "File uploaded successfully: /docs/note.txt"


# ─────────────────────────── Multipart upload ────────────────────────────


@pytest.mark.asyncio
async def test_upload_file_multipart_happy_path(transfer_tools) -> None:
    tools, client = transfer_tools

    # "hello" is 5 bytes → exactly one chunk
    result = json.loads(await tools["upload_file_multipart"]("/docs", "big.bin", "aGVsbG8="))

    assert result["ok"] is True
    assert result["upload_id"] == "up-1"
    assert result["chunks_sent"] == 1
    assert client.multipart_calls == [
        {
            "method": "init",
            "file_path": "/docs/big.bin",
            "file_size": 5,
            "chunk_size": 8 * 1024 * 1024,
            "overwrite": True,
            "file_md5": "5d41402abc4b2a76b9719d911017c592",  # md5("hello")
        },
        {"method": "chunk", "upload_id": "up-1", "index": 0, "size": 5},
        {"method": "complete", "upload_id": "up-1"},
    ]


@pytest.mark.asyncio
async def test_upload_file_multipart_multi_chunk(transfer_tools) -> None:
    tools, client = transfer_tools
    import base64

    # ~2 MiB + 10 bytes with 1 MiB chunks → chunks 0..2
    data = b"a" * (2 * 1024 * 1024 + 10)
    result = json.loads(
        await tools["upload_file_multipart"](
            "/docs", "x.bin", base64.b64encode(data).decode(), chunk_size=1024 * 1024
        )
    )

    assert result["ok"] is True
    assert result["chunks_sent"] == 3
    indexes = [c["index"] for c in client.multipart_calls if c["method"] == "chunk"]
    assert indexes == [0, 1, 2]


@pytest.mark.asyncio
async def test_upload_file_multipart_chunk_size_floored_to_1mib(transfer_tools) -> None:
    tools, client = transfer_tools

    await tools["upload_file_multipart"]("/docs", "x.bin", "YQ==", chunk_size=100)

    init = next(c for c in client.multipart_calls if c["method"] == "init")
    assert init["chunk_size"] == 1024 * 1024


@pytest.mark.asyncio
async def test_upload_file_multipart_rejects_bad_base64(transfer_tools) -> None:
    tools, client = transfer_tools

    result = json.loads(await tools["upload_file_multipart"]("/docs", "x.bin", "!!!not-base64!!!"))

    assert result["ok"] is False
    assert client.multipart_calls == []


@pytest.mark.asyncio
async def test_upload_file_multipart_rejects_empty_file(transfer_tools) -> None:
    tools, client = transfer_tools

    result = json.loads(await tools["upload_file_multipart"]("/docs", "empty.bin", ""))

    assert result["ok"] is False
    assert "empty" in result["error"].lower()
    assert client.multipart_calls == []


@pytest.mark.asyncio
async def test_upload_file_multipart_resume_skips_received_chunks(transfer_tools) -> None:
    tools, client = transfer_tools
    import base64

    client.resume_received = [[0, 0]]

    # ~2 MiB with 1 MiB chunks → chunks 0 and 1; chunk 0 already received
    data = b"b" * (2 * 1024 * 1024)
    result = json.loads(
        await tools["upload_file_multipart"](
            "/docs", "r.bin", base64.b64encode(data).decode(), chunk_size=1024 * 1024
        )
    )

    assert result["ok"] is True
    assert result["chunks_sent"] == 2  # 1 skipped + 1 uploaded
    indexes = [c["index"] for c in client.multipart_calls if c["method"] == "chunk"]
    assert indexes == [1]


@pytest.mark.asyncio
async def test_multipart_init_sends_file_md5_identity_proof(transfer_tools) -> None:
    """Resume requires a hash proving the retry is the same file (post-v4.2.5)."""
    import base64
    import hashlib

    tools, client = transfer_tools
    data = b"identity proof payload"
    await tools["upload_file_multipart"](
        "/docs", "r.bin", base64.b64encode(data).decode(), chunk_size=1024 * 1024
    )

    inits = [c for c in client.multipart_calls if c["method"] == "init"]
    assert inits and inits[0]["file_md5"] == hashlib.md5(data).hexdigest()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_multipart_uses_server_chunk_size_for_slicing(transfer_tools, monkeypatch) -> None:
    """Slicing must follow the session chunk size from init, not the local one."""
    import base64

    tools, client = transfer_tools

    class ServerClampedClient:
        """Proxy whose init returns a clamped (larger) chunk size than requested."""

        def __init__(self, fake) -> None:
            self._fake = fake

        def __getattr__(self, item):
            return getattr(self._fake, item)

        async def multipart_init(
            self, file_path, file_size, chunk_size=None, overwrite=True, file_md5=None
        ):
            self._fake.multipart_calls.append(
                {
                    "method": "init",
                    "file_path": file_path,
                    "file_size": file_size,
                    "chunk_size": chunk_size,
                    "overwrite": overwrite,
                    "file_md5": file_md5,
                }
            )
            return {
                "upload_id": "up-1",
                "state": "uploading",
                "path": file_path,
                "size": file_size,
                "chunk_size": 2 * 1024 * 1024,
                "received": [],
                "received_bytes": 0,
            }  # server clamps to 2MiB

        async def multipart_chunk(self, upload_id, index, chunk):
            self._fake.multipart_calls.append(
                {"method": "chunk", "index": index, "chunk_len": len(chunk)}
            )

        async def multipart_complete(self, upload_id):
            return {"state": "completed"}

    async def fake_get_client():
        return ServerClampedClient(client)

    monkeypatch.setattr("openlist_mcp.tools.transfer.get_client", fake_get_client)

    # 4 MiB with a requested 1 MiB chunk but server-clamped 2 MiB -> 2 chunks
    data = b"c" * (4 * 1024 * 1024)
    result = json.loads(
        await tools["upload_file_multipart"](
            "/docs", "s.bin", base64.b64encode(data).decode(), chunk_size=1024 * 1024
        )
    )

    assert result["ok"] is True
    assert result["total_chunks"] == 2
    chunks = [c for c in client.multipart_calls if c["method"] == "chunk"]
    assert [c["chunk_len"] for c in chunks] == [2 * 1024 * 1024, 2 * 1024 * 1024]


@pytest.mark.asyncio
async def test_upload_file_multipart_chunk_failure_reports_resume_info(transfer_tools) -> None:
    tools, client = transfer_tools
    import base64

    client.fail_chunk_index = 1

    # ~2 MiB with 1 MiB chunks → chunk 1 fails
    data = b"a" * (2 * 1024 * 1024)
    result = json.loads(
        await tools["upload_file_multipart"](
            "/docs", "f.bin", base64.b64encode(data).decode(), chunk_size=1024 * 1024
        )
    )

    assert result["ok"] is False
    assert result["upload_id"] == "up-1"
    assert "chunk 1" in result["error"][0]
    assert "resume_hint" in result
    # status probe was made after the failure
    assert any(c["method"] == "status" for c in client.multipart_calls)


@pytest.mark.asyncio
async def test_upload_file_multipart_respects_readonly(transfer_tools, monkeypatch) -> None:
    tools, client = transfer_tools
    monkeypatch.setenv("OPENLIST_READONLY", "true")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="OPENLIST_READONLY"):
        await tools["upload_file_multipart"]("/docs", "x.bin", "aGVsbG8=")
    assert client.multipart_calls == []


@pytest.mark.asyncio
async def test_upload_file_multipart_respects_allowed_paths(transfer_tools, monkeypatch) -> None:
    tools, client = transfer_tools
    monkeypatch.setenv("OPENLIST_ALLOWED_PATHS", "/safe")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="outside OPENLIST_ALLOWED_PATHS"):
        await tools["upload_file_multipart"]("/private", "x.bin", "aGVsbG8=")
    assert client.multipart_calls == []


@pytest.mark.asyncio
async def test_multipart_upload_status_by_id(transfer_tools) -> None:
    tools, client = transfer_tools

    await tools["multipart_upload_status"](upload_id="up-9")

    assert client.multipart_calls == [
        {"method": "status", "upload_id": "up-9", "path": "", "file_size": 0}
    ]


@pytest.mark.asyncio
async def test_multipart_upload_status_by_path_and_size(transfer_tools) -> None:
    tools, client = transfer_tools

    await tools["multipart_upload_status"](path="/docs/big.bin", file_size=1024)

    assert client.multipart_calls == [
        {"method": "status", "upload_id": "", "path": "/docs/big.bin", "file_size": 1024}
    ]


@pytest.mark.asyncio
async def test_multipart_upload_status_requires_identifier(transfer_tools) -> None:
    tools, client = transfer_tools

    with pytest.raises(ValueError, match="requires upload_id"):
        await tools["multipart_upload_status"]()


@pytest.mark.asyncio
async def test_multipart_abort_requires_confirm(transfer_tools) -> None:
    tools, client = transfer_tools

    result = await tools["multipart_abort_upload"]("up-1", confirm=False)

    assert "not performed" in result.lower()
    assert client.multipart_calls == []


@pytest.mark.asyncio
async def test_multipart_abort_success(transfer_tools) -> None:
    tools, client = transfer_tools

    result = await tools["multipart_abort_upload"]("up-1", confirm=True)

    assert "aborted" in result.lower()
    assert client.multipart_calls == [{"method": "abort", "upload_id": "up-1"}]


@pytest.mark.asyncio
async def test_multipart_local_upload_requires_allowed_root(
    transfer_tools, monkeypatch, tmp_path
) -> None:
    tools, client = transfer_tools
    monkeypatch.delenv("OPENLIST_LOCAL_UPLOAD_ROOTS", raising=False)
    monkeypatch.setattr("openlist_mcp.config._config", None)

    local = tmp_path / "large.bin"
    local.write_bytes(b"x" * 2048)

    result = json.loads(await tools["multipart_upload_local_file"](str(local), "/docs", local.name))

    assert result["ok"] is False
    assert "OPENLIST_LOCAL_UPLOAD_ROOTS" in result["error"]
    assert client.multipart_calls == []


@pytest.mark.asyncio
async def test_multipart_local_upload_streams_chunks(transfer_tools, monkeypatch, tmp_path) -> None:
    tools, client = transfer_tools
    monkeypatch.setenv("OPENLIST_LOCAL_UPLOAD_ROOTS", str(tmp_path))
    monkeypatch.setattr("openlist_mcp.config._config", None)

    local = tmp_path / "large.bin"
    local.write_bytes(b"01234567" * (256 * 1024))  # 2 MiB

    result = json.loads(
        await tools["multipart_upload_local_file"](
            str(local), "/docs", local.name, chunk_size=1024 * 1024
        )
    )

    assert result["ok"] is True
    assert result["chunks_sent"] == 2
    init = next(c for c in client.multipart_calls if c["method"] == "init")
    assert init["file_size"] == 2 * 1024 * 1024
    assert init["file_path"] == "/docs/large.bin"


# ─────────────────────────── Direct upload info ──────────────────────────


@pytest.mark.asyncio
async def test_get_direct_upload_info_sends_payload(transfer_tools) -> None:
    tools, client = transfer_tools

    await tools["get_direct_upload_info"]("/docs", "video.mp4", 1000)

    assert client.requests == [
        (
            "POST",
            "fs/get_direct_upload_info",
            {
                "json": {
                    "path": "/docs",
                    "file_name": "video.mp4",
                    "file_size": 1000,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_direct_upload_info_includes_tool(transfer_tools) -> None:
    tools, client = transfer_tools

    await tools["get_direct_upload_info"]("/docs", "video.mp4", 1000, tool="s3")

    assert client.requests[0][2]["json"]["tool"] == "s3"


@pytest.mark.asyncio
async def test_get_direct_upload_info_rejects_bad_size(transfer_tools) -> None:
    tools, client = transfer_tools

    result = json.loads(await tools["get_direct_upload_info"]("/docs", "x.txt", 0))

    assert result["ok"] is False
    assert client.requests == []
