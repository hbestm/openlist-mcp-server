"""Behavior tests for advanced MCP tools."""

import pytest


@pytest.mark.asyncio
async def test_get_capabilities_summarizes_server_user_and_tools(advanced_tools) -> None:
    tools, client = advanced_tools

    result = await tools["get_capabilities"]()

    assert '"base_url": "https://openlist.example"' in result
    assert '"uses_https": true' in result
    assert '"username": "admin"' in result
    assert '"offline_download_tools": [\n      "aria2"\n    ]' in result
    assert client.requests == [
        ("GET", "public/settings", {"require_auth": False}),
        ("GET", "me", {}),
        ("GET", "public/offline_download_tools", {"require_auth": False}),
    ]


@pytest.mark.asyncio
async def test_list_archive_files_validates_archive_name(advanced_tools) -> None:
    tools, client = advanced_tools

    with pytest.raises(ValueError, match="path separators"):
        await tools["list_archive_files"]("/archives", "bad/name.zip")

    assert client.requests == []


@pytest.mark.asyncio
async def test_list_archive_files_sends_expected_payload(advanced_tools) -> None:
    tools, client = advanced_tools

    result = await tools["list_archive_files"](
        "/archives",
        "bundle.zip",
        inner_path="/docs",
        archive_pass="secret",
        refresh=True,
    )

    assert result == "{}"
    assert client.requests == [
        (
            "POST",
            "fs/archive/list",
            {
                "json": {
                    "path": "/archives/bundle.zip",
                    "inner_path": "/docs",
                    "refresh": True,
                    "archive_pass": "secret",
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_archive_meta_sends_path(advanced_tools) -> None:
    tools, client = advanced_tools

    await tools["get_archive_meta"]("/data/backup.zip")

    assert client.requests == [
        ("POST", "fs/archive/meta", {"json": {"path": "/data/backup.zip", "refresh": False}})
    ]


@pytest.mark.asyncio
async def test_get_archive_meta_with_pass_and_refresh(advanced_tools) -> None:
    tools, client = advanced_tools

    await tools["get_archive_meta"](
        "/data/encrypted.7z",
        archive_pass="hunter2",
        refresh=True,
    )

    assert client.requests == [
        (
            "POST",
            "fs/archive/meta",
            {
                "json": {
                    "path": "/data/encrypted.7z",
                    "refresh": True,
                    "archive_pass": "hunter2",
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_torrent_upload_parse_sends_multipart(advanced_tools) -> None:
    tools, client = advanced_tools

    result = await tools["torrent_upload_parse"]("ZGVhZGJlZWY=")

    assert client.requests == [
        (
            "MULTIPART",
            "fs/torrent/upload_parse",
            {
                "field_name": "torrent",
                "file_name": "file.torrent",
                "content_type": "application/x-bittorrent",
                "size": 8,
            },
        )
    ]
    assert '"info_hash"' in result
    assert '"torrent_data"' in result


@pytest.mark.asyncio
async def test_find_duplicates_respects_allowed_paths(advanced_tools, monkeypatch) -> None:
    tools, client = advanced_tools
    monkeypatch.setenv("OPENLIST_ALLOWED_PATHS", "/safe")
    monkeypatch.setenv("OPENLIST_USERNAME", "admin")
    monkeypatch.setenv("OPENLIST_PASSWORD", "secret")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="outside OPENLIST_ALLOWED_PATHS"):
        await tools["find_duplicates"]("/private")

    assert client.requests == []
