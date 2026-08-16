"""Behavior tests for admin MCP tools (read-only and write operations)."""

from __future__ import annotations

import pytest

# ─────────────────────────── Storage ────────────────────────────


@pytest.mark.asyncio
async def test_list_storages_sends_get_request(admin_tools) -> None:
    tools, client = admin_tools

    await tools["list_storages"]()

    assert client.requests == [("GET", "admin/storage/list", {})]


@pytest.mark.asyncio
async def test_get_storage_info_passes_id_param(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_storage_info"](storage_id=2)

    assert client.requests == [("GET", "admin/storage/get", {"params": {"id": 2}})]


# ─────────────────────────── Driver ─────────────────────────────


@pytest.mark.asyncio
async def test_list_drivers_sends_get_request(admin_tools) -> None:
    tools, client = admin_tools

    await tools["list_drivers"]()

    assert client.requests == [("GET", "admin/driver/names", {})]


@pytest.mark.asyncio
async def test_get_driver_info_passes_driver_param(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_driver_info"](driver="S3")

    assert client.requests == [("GET", "admin/driver/info", {"params": {"driver": "S3"}})]


@pytest.mark.asyncio
async def test_list_drivers_detail_sends_get_request(admin_tools) -> None:
    tools, client = admin_tools

    await tools["list_drivers_detail"]()

    assert client.requests == [("GET", "admin/driver/list", {})]


# ─────────────────────────── Settings ───────────────────────────


@pytest.mark.asyncio
async def test_get_settings_sends_get_request(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_settings"]()

    assert client.requests == [("GET", "admin/setting/list", {})]


@pytest.mark.asyncio
async def test_get_setting_passes_key_param(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_setting"](key="site_title")

    assert client.requests == [("GET", "admin/setting/get", {"params": {"key": "site_title"}})]


@pytest.mark.asyncio
async def test_save_settings_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["save_settings"](settings=[{"key": "a", "value": "1"}])

    assert "not performed" in result
    assert "confirm=true" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_save_settings_empty_list(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["save_settings"](settings=[], confirm=True)

    assert "No settings" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_save_settings_sends_post_request(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["save_settings"](
        settings=[{"key": "site_title", "value": "My Cloud"}],
        confirm=True,
    )

    assert "saved successfully" in result
    assert client.requests == [
        (
            "POST",
            "admin/setting/save",
            {"json": [{"key": "site_title", "value": "My Cloud"}]},
        )
    ]


@pytest.mark.asyncio
async def test_save_settings_multiple_keys(admin_tools) -> None:
    tools, client = admin_tools

    settings = [
        {"key": "site_title", "value": "My Cloud"},
        {"key": "pagination_type", "value": "0"},
    ]
    result = await tools["save_settings"](settings=settings, confirm=True)

    assert "2 key(s)" in result
    assert client.requests == [("POST", "admin/setting/save", {"json": settings})]


@pytest.mark.asyncio
async def test_delete_setting_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["delete_setting"](key="custom_logo")

    assert "not performed" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_delete_setting_empty_key(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["delete_setting"](key="", confirm=True)

    assert "No setting key" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_delete_setting_sends_post_request(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["delete_setting"](key="custom_logo", confirm=True)

    assert "deleted successfully" in result
    assert client.requests == [("POST", "admin/setting/delete", {"json": {"key": "custom_logo"}})]


# ─────────────────────────── Search Index ───────────────────────


@pytest.mark.asyncio
async def test_get_index_progress_sends_get_request(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_index_progress"]()

    assert client.requests == [("GET", "admin/index/progress", {})]


@pytest.mark.asyncio
async def test_build_search_index_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["build_search_index"]()

    assert "not performed" in result
    assert "confirm=true" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_build_search_index_sends_post_request(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["build_search_index"](confirm=True)

    assert "build started" in result
    assert client.requests == [("POST", "admin/index/build", {})]


@pytest.mark.asyncio
async def test_update_search_index_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["update_search_index"]()

    assert "not performed" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_update_search_index_with_paths(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["update_search_index"](
        paths=["/documents", "/downloads"],
        confirm=True,
    )

    assert "update started" in result
    assert client.requests == [
        (
            "POST",
            "admin/index/update",
            {"json": {"paths": ["/documents", "/downloads"]}},
        )
    ]


@pytest.mark.asyncio
async def test_update_search_index_no_paths(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["update_search_index"](confirm=True)

    assert "update started" in result
    assert client.requests == [("POST", "admin/index/update", {"json": {}})]


@pytest.mark.asyncio
async def test_stop_indexing_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["stop_indexing"]()

    assert "not performed" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_stop_indexing_sends_post_request(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["stop_indexing"](confirm=True)

    assert "stopped" in result
    assert client.requests == [("POST", "admin/index/stop", {})]


@pytest.mark.asyncio
async def test_clear_search_index_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["clear_search_index"]()

    assert "not performed" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_clear_search_index_sends_post_request(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["clear_search_index"](confirm=True)

    assert "cleared" in result
    assert client.requests == [("POST", "admin/index/clear", {})]


# ─────────────────────────── User Management ────────────────────


@pytest.mark.asyncio
async def test_list_users_defaults_page_per_page(admin_tools) -> None:
    tools, client = admin_tools

    await tools["list_users"]()

    assert client.requests == [("GET", "admin/user/list", {"params": {"page": 1, "per_page": 30}})]


@pytest.mark.asyncio
async def test_list_users_custom_pagination(admin_tools) -> None:
    tools, client = admin_tools

    await tools["list_users"](page=2, per_page=10)

    assert client.requests == [("GET", "admin/user/list", {"params": {"page": 2, "per_page": 10}})]


@pytest.mark.asyncio
async def test_list_users_rejects_invalid_page(admin_tools) -> None:
    tools, client = admin_tools

    with pytest.raises(ValueError):
        await tools["list_users"](page=0)


@pytest.mark.asyncio
async def test_get_user_passes_id_param(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_user"](user_id=5)

    assert client.requests == [("GET", "admin/user/get", {"params": {"id": 5}})]


# ─────────────────────────── Meta Management ────────────────────


@pytest.mark.asyncio
async def test_list_metas_sends_get_request(admin_tools) -> None:
    tools, client = admin_tools

    await tools["list_metas"]()

    assert client.requests == [("GET", "admin/meta/list", {})]


@pytest.mark.asyncio
async def test_get_meta_passes_id_param(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_meta"](meta_id=3)

    assert client.requests == [("GET", "admin/meta/get", {"params": {"id": 3}})]


# ─────────────────────────── Token Management ───────────────────


@pytest.mark.asyncio
async def test_reset_api_token_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["reset_api_token"]()

    assert "not performed" in result
    assert "confirm=true" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_reset_api_token_sends_post_request(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["reset_api_token"](confirm=True)

    assert "reset successfully" in result
    assert client.requests == [("POST", "admin/setting/reset_token", {})]


# ─────────────────────────── Manual Scan ────────────────────────────


@pytest.mark.asyncio
async def test_start_manual_scan_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["start_manual_scan"]("/my-drive")

    assert "not started" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_start_manual_scan_sends_payload(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["start_manual_scan"]("/my-drive", limit=500, confirm=True)

    assert "started" in result
    assert client.requests == [
        ("POST", "admin/scan/start", {"json": {"path": "/my-drive", "limit": 500.0}})
    ]


@pytest.mark.asyncio
async def test_start_manual_scan_omits_zero_limit(admin_tools) -> None:
    tools, client = admin_tools

    await tools["start_manual_scan"]("/my-drive", confirm=True)

    assert client.requests == [("POST", "admin/scan/start", {"json": {"path": "/my-drive"}})]


@pytest.mark.asyncio
async def test_stop_manual_scan_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["stop_manual_scan"]()

    assert "not performed" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_stop_manual_scan_sends_post_request(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["stop_manual_scan"](confirm=True)

    assert "stopped" in result
    assert client.requests == [("POST", "admin/scan/stop", {})]


@pytest.mark.asyncio
async def test_get_manual_scan_progress_sends_get_request(admin_tools) -> None:
    tools, client = admin_tools

    await tools["get_manual_scan_progress"]()

    assert client.requests == [("GET", "admin/scan/progress", {})]


@pytest.mark.asyncio
async def test_scan_tools_respect_readonly(admin_tools, monkeypatch) -> None:
    tools, client = admin_tools
    monkeypatch.setenv("OPENLIST_READONLY", "true")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    with pytest.raises(PermissionError, match="OPENLIST_READONLY"):
        await tools["start_manual_scan"]("/my-drive", confirm=True)

    assert client.requests == []
