"""Behavior tests for filesystem MCP tools."""

import pytest


@pytest.mark.asyncio
async def test_create_folder_uses_mkdir_without_name_validation(fs_tools) -> None:
    tools, client = fs_tools

    result = await tools["create_folder"]("/projects/new")

    assert result == "Folder created successfully: /projects/new"
    assert client.requests == [("POST", "fs/mkdir", {"json": {"path": "/projects/new"}})]


@pytest.mark.asyncio
async def test_read_only_blocks_write_tools(fs_tools, monkeypatch) -> None:
    tools, client = fs_tools
    monkeypatch.setenv("OPENLIST_READONLY", "true")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="OPENLIST_READONLY"):
        await tools["create_folder"]("/projects/new")

    assert client.requests == []


@pytest.mark.asyncio
async def test_allowed_paths_blocks_out_of_scope_reads(fs_tools, monkeypatch) -> None:
    tools, client = fs_tools
    monkeypatch.setenv("OPENLIST_ALLOWED_PATHS", "/safe,/team/docs")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="outside OPENLIST_ALLOWED_PATHS"):
        await tools["list_files"]("/private")

    assert client.requests == []


@pytest.mark.asyncio
async def test_allowed_paths_allows_child_paths(fs_tools, monkeypatch) -> None:
    tools, client = fs_tools
    monkeypatch.setenv("OPENLIST_ALLOWED_PATHS", "/safe")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    await tools["list_files"]("/safe/nested")

    assert client.requests == [
        (
            "POST",
            "fs/list",
            {
                "json": {
                    "path": "/safe/nested",
                    "page": 1,
                    "per_page": 50,
                    "password": "",
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_list_dirs_sends_expected_payload(fs_tools) -> None:
    tools, client = fs_tools

    result = await tools["list_dirs"]("/projects", password="secret", force_root=True)

    assert result == "{}"
    assert client.requests == [
        (
            "POST",
            "fs/dirs",
            {
                "json": {
                    "path": "/projects",
                    "password": "secret",
                    "force_root": True,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_rename_validates_new_name(fs_tools) -> None:
    tools, client = fs_tools

    with pytest.raises(ValueError, match="path separators"):
        await tools["rename"]("/projects/old", "../bad")

    assert client.requests == []


@pytest.mark.asyncio
async def test_rename_sends_expected_payload(fs_tools) -> None:
    tools, client = fs_tools

    result = await tools["rename"]("/projects/old", "new")

    assert result == "Renamed successfully: /projects/old -> new"
    assert client.requests == [
        ("POST", "fs/rename", {"json": {"path": "/projects/old", "name": "new"}})
    ]


@pytest.mark.asyncio
async def test_batch_rename_validates_names(fs_tools) -> None:
    tools, client = fs_tools

    with pytest.raises(ValueError, match="path separators"):
        await tools["batch_rename"](
            "/projects",
            [{"src_name": "good.txt", "new_name": "bad/name.txt"}],
        )

    assert client.requests == []


@pytest.mark.asyncio
async def test_batch_rename_sends_expected_payload(fs_tools) -> None:
    tools, client = fs_tools

    result = await tools["batch_rename"](
        "/projects",
        [
            {"src_name": "old-a.txt", "new_name": "new-a.txt"},
            {"src_name": "old-b.txt", "new_name": "new-b.txt"},
        ],
    )

    assert result.startswith("Batch renamed successfully in /projects")
    assert client.requests == [
        (
            "POST",
            "fs/batch_rename",
            {
                "json": {
                    "src_dir": "/projects",
                    "rename_objects": [
                        {"src_name": "old-a.txt", "new_name": "new-a.txt"},
                        {"src_name": "old-b.txt", "new_name": "new-b.txt"},
                    ],
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_copy_validates_each_name(fs_tools) -> None:
    tools, client = fs_tools

    with pytest.raises(ValueError, match="path separators"):
        await tools["copy"]("/src", "/dst", ["good.txt", "bad/name.txt"])

    assert client.requests == []


@pytest.mark.asyncio
async def test_tree_respects_allowed_paths(fs_tools, monkeypatch) -> None:
    tools, client = fs_tools
    monkeypatch.setenv("OPENLIST_ALLOWED_PATHS", "/safe")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="outside OPENLIST_ALLOWED_PATHS"):
        await tools["tree"]("/private")

    assert client.requests == []


@pytest.mark.asyncio
async def test_disk_usage_respects_allowed_paths(fs_tools, monkeypatch) -> None:
    tools, client = fs_tools
    monkeypatch.setenv("OPENLIST_ALLOWED_PATHS", "/safe")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="outside OPENLIST_ALLOWED_PATHS"):
        await tools["disk_usage"]("/private")

    assert client.requests == []
