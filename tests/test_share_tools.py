"""Behavior tests for share management MCP tools."""

import pytest


@pytest.mark.asyncio
async def test_create_share_sends_files_array(share_tools) -> None:
    tools, client = share_tools

    await tools["create_share"](
        files=["/docs/report.pdf", "/docs/summary.csv"],
        pwd="secret",
    )

    assert client.requests == [
        (
            "POST",
            "share/create",
            {
                "json": {
                    "files": ["/docs/report.pdf", "/docs/summary.csv"],
                    "pwd": "secret",
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_create_share_rejects_empty_files(share_tools) -> None:
    tools, client = share_tools

    result = await tools["create_share"](files=[])

    assert "error" in result.lower() or "must" in result.lower()
    assert client.requests == []


@pytest.mark.asyncio
async def test_update_share_sends_id_and_files(share_tools) -> None:
    tools, client = share_tools

    await tools["update_share"](
        share_id="abc123",
        files=["/docs/report.pdf"],
        pwd="newpass",
    )

    assert client.requests == [
        (
            "POST",
            "share/update",
            {
                "json": {
                    "id": "abc123",
                    "files": ["/docs/report.pdf"],
                    "pwd": "newpass",
                }
            },
        ),
    ]


@pytest.mark.asyncio
async def test_disable_share_sends_query_param(share_tools) -> None:
    tools, client = share_tools

    await tools["disable_share"](share_id="abc123")

    # OpenList reads ?id= from the query string for share/disable, not the body.
    assert client.requests == [("POST", "share/disable", {"params": {"id": "abc123"}})]


@pytest.mark.asyncio
async def test_enable_share_sends_query_param(share_tools) -> None:
    tools, client = share_tools

    await tools["enable_share"](share_id="abc123")

    assert client.requests == [("POST", "share/enable", {"params": {"id": "abc123"}})]


@pytest.mark.asyncio
async def test_cancel_share_sends_query_param(share_tools) -> None:
    tools, client = share_tools

    await tools["cancel_share"](share_id="abc123", confirm=True)

    assert client.requests == [("POST", "share/disable", {"params": {"id": "abc123"}})]


@pytest.mark.asyncio
async def test_delete_share_requires_confirm(share_tools) -> None:
    tools, client = share_tools

    result = await tools["delete_share"](share_id="abc123", confirm=False)

    assert "not performed" in result.lower()
    assert client.requests == []


@pytest.mark.asyncio
async def test_delete_share_with_confirm_uses_query_param(share_tools) -> None:
    tools, client = share_tools

    await tools["delete_share"](share_id="abc123", confirm=True)

    assert client.requests == [("POST", "share/delete", {"params": {"id": "abc123"}})]


@pytest.mark.asyncio
async def test_read_only_blocks_share_write_tools(share_tools, monkeypatch) -> None:
    tools, client = share_tools
    monkeypatch.setenv("OPENLIST_READONLY", "true")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="OPENLIST_READONLY"):
        await tools["create_share"](files=["/test.txt"])

    assert client.requests == []


@pytest.mark.asyncio
async def test_allowed_paths_blocks_out_of_scope_files(share_tools, monkeypatch) -> None:
    tools, client = share_tools
    monkeypatch.setenv("OPENLIST_ALLOWED_PATHS", "/safe")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="outside OPENLIST_ALLOWED_PATHS"):
        await tools["create_share"](files=["/private/file.txt"])

    assert client.requests == []
