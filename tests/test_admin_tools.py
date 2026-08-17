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
    assert client.requests == [("POST", "admin/setting/delete", {"params": {"key": "custom_logo"}})]


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


def _admin_fake_get_client(real_client, existing):
    """Async get_client() whose GET admin/{storage,user}/get returns `existing`
    (so update_storage / update_user can read-then-merge) while all other
    requests are recorded on the real FakeClient."""

    class _Proxy:
        async def request(self, method, path, **kwargs):
            real_client.requests.append((method, path, kwargs))
            if method == "GET" and path in ("admin/storage/get", "admin/user/get"):
                return existing
            return {}

    async def fake_get_client():
        return _Proxy()

    return fake_get_client


# ─────────────────────────── Storage (write) ──────────────────


@pytest.mark.asyncio
async def test_create_storage_sends_full_payload(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["create_storage"](
        mount_path="backup",
        driver="Local",
        addition='{"root_folder_path": "/data"}',
        remark="tests",
        confirm=True,
    )

    assert "Storage created: Local at /backup" in result
    ((method, path, kwargs),) = client.requests
    assert method == "POST" and path == "admin/storage/create"
    assert kwargs["json"]["mount_path"] == "/backup"
    assert kwargs["json"]["driver"] == "Local"
    assert kwargs["json"]["addition"] == '{"root_folder_path": "/data"}'
    assert kwargs["json"]["remark"] == "tests"
    assert kwargs["json"]["disabled"] is False


@pytest.mark.asyncio
async def test_create_storage_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["create_storage"]("backup", "Local", confirm=False)

    assert "confirm=true" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_create_storage_rejects_bad_addition(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["create_storage"]("/backup", "Local", addition="not-json", confirm=True)

    assert "JSON object" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_update_storage_reads_then_merges(admin_tools, monkeypatch) -> None:
    tools, client = admin_tools
    monkeypatch.setattr(
        "openlist_mcp.tools.admin.get_client",
        _admin_fake_get_client(
            client,
            existing={
                "id": 7,
                "mount_path": "/old",
                "driver": "Local",
                "addition": "{}",
                "remark": "orig",
                "order": 1,
                "cache_expiration": 0,
                "disabled": False,
                "disable_index": False,
                "enable_sign": False,
                "status": "work",
            },
        ),
    )

    result = await tools["update_storage"](7, remark="changed", confirm=True)

    assert "Storage updated: id=7" in result
    ops = [r for r in client.requests if r[1].endswith(("storage/get", "storage/update"))]
    assert ("GET", "admin/storage/get", {"params": {"id": 7}}) in ops
    (method, path, kwargs) = [r for r in client.requests if r[1] == "admin/storage/update"][0]
    assert kwargs["json"]["id"] == 7
    assert kwargs["json"]["remark"] == "changed"
    assert kwargs["json"]["mount_path"] == "/old"  # untouched field preserved
    assert kwargs["json"]["driver"] == "Local"


@pytest.mark.asyncio
async def test_delete_enable_disable_use_query_param(admin_tools) -> None:
    tools, client = admin_tools

    for name, path in (
        ("delete_storage", "admin/storage/delete"),
        ("enable_storage", "admin/storage/enable"),
        ("disable_storage", "admin/storage/disable"),
    ):
        client.requests.clear()
        result = await tools[name](3, confirm=True)
        assert "id=3" in result
        assert client.requests == [("POST", path, {"params": {"id": 3}})]


@pytest.mark.asyncio
async def test_load_all_storages_posts_without_body(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["load_all_storages"](confirm=True)

    assert "reloaded" in result
    assert client.requests == [("POST", "admin/storage/load_all", {})]


@pytest.mark.asyncio
async def test_storage_write_tools_respect_readonly(admin_tools, monkeypatch) -> None:
    tools, client = admin_tools
    monkeypatch.setenv("OPENLIST_READONLY", "true")
    monkeypatch.setattr("openlist_mcp.config._config", None)

    for name, args in (
        ("create_storage", ("/x", "Local")),
        ("delete_storage", (1,)),
        ("enable_storage", (1,)),
        ("disable_storage", (1,)),
        ("load_all_storages", ()),
    ):
        with pytest.raises(PermissionError, match="OPENLIST_READONLY"):
            await tools[name](*args, confirm=True)
    assert client.requests == []


# ─────────────────── Driver / download clients (write) ────────


@pytest.mark.asyncio
async def test_set_aria2_posts_uri_and_secret(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["set_aria2"]("http://127.0.0.1:6800/jsonrpc", "tok", confirm=True)

    assert "aria2 configured" in result
    assert client.requests == [
        (
            "POST",
            "admin/setting/set_aria2",
            {"json": {"uri": "http://127.0.0.1:6800/jsonrpc", "secret": "tok"}},
        )
    ]


@pytest.mark.asyncio
async def test_set_aria2_requires_uri(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["set_aria2"](confirm=True)

    assert "uri is required" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_set_qbittorrent_posts_url_and_seedtime(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["set_qbittorrent"]("http://127.0.0.1:8080", "120", confirm=True)

    assert "qBittorrent configured" in result
    assert client.requests == [
        (
            "POST",
            "admin/setting/set_qbit",
            {"json": {"url": "http://127.0.0.1:8080", "seedtime": "120"}},
        )
    ]


@pytest.mark.asyncio
async def test_set_transmission_posts_uri(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["set_transmission"]("http://127.0.0.1:9091/rpc", confirm=True)

    assert "Transmission configured" in result
    assert client.requests == [
        (
            "POST",
            "admin/setting/set_transmission",
            {"json": {"uri": "http://127.0.0.1:9091/rpc", "seedtime": ""}},
        )
    ]


@pytest.mark.asyncio
async def test_temp_dir_setters_post_temp_dir(admin_tools) -> None:
    tools, client = admin_tools
    cases = [
        ("set_115", "admin/setting/set_115", "115"),
        ("set_115_open", "admin/setting/set_115_open", "115 Open"),
        ("set_123_pan", "admin/setting/set_123_pan", "123 Pan"),
        ("set_pikpak", "admin/setting/set_pikpak", "PikPak"),
        ("set_thunder", "admin/setting/set_thunder", "Thunder"),
        ("set_thunderx", "admin/setting/set_thunderx", "ThunderX"),
        ("set_thunder_browser", "admin/setting/set_thunder_browser", "Thunder Browser"),
        ("set_guangyapan", "admin/setting/set_guangyapan", "GuangYaPan"),
    ]
    for tool_name, endpoint, display in cases:
        client.requests.clear()
        result = await tools[tool_name]("/tmp/dl", confirm=True)
        assert f"{display} configured" in result, tool_name
        assert client.requests == [("POST", endpoint, {"json": {"temp_dir": "/tmp/dl"}})], tool_name


@pytest.mark.asyncio
async def test_set_123_open_posts_callback_url(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["set_123_open"]("/tmp/dl", "https://cb.example/x", confirm=True)

    assert "123 Open configured" in result
    assert client.requests == [
        (
            "POST",
            "admin/setting/set_123_open",
            {"json": {"temp_dir": "/tmp/dl", "callback_url": "https://cb.example/x"}},
        )
    ]


@pytest.mark.asyncio
async def test_driver_setters_require_confirm_and_temp_dir(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["set_115"]("/tmp/dl", confirm=False)
    assert "confirm=true" in result
    assert client.requests == []

    result = await tools["set_pikpak"](confirm=True)
    assert "temp_dir is required" in result
    assert client.requests == []


# ─────────────────── Users (write) ────────────────────────────


@pytest.mark.asyncio
async def test_create_user_posts_minimal_payload(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["create_user"]("alice", password="pw123", confirm=True)

    assert "User created: alice" in result
    ((method, path, kwargs),) = client.requests
    assert method == "POST" and path == "admin/user/create"
    body = kwargs["json"]
    assert body["username"] == "alice"
    assert body["password"] == "pw123"
    assert body["role"] == 0
    assert body["base_path"] == "/"
    assert body["permission"] == 53247  # DEFAULT_USER_PERMISSION
    assert body["disabled"] is False


@pytest.mark.asyncio
async def test_create_user_rejects_admin_role(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["create_user"]("root", role="admin", confirm=True)

    assert "cannot create guest/admin" in result
    assert client.requests == []


@pytest.mark.asyncio
async def test_update_user_reads_then_merges(admin_tools, monkeypatch) -> None:
    tools, client = admin_tools
    monkeypatch.setattr(
        "openlist_mcp.tools.admin.get_client",
        _admin_fake_get_client(
            client,
            existing={
                "id": 5,
                "username": "bob",
                "base_path": "/",
                "role": 0,
                "disabled": False,
                "permission": 53247,
                "sso_id": "",
                "allow_ldap": True,
            },
        ),
    )

    result = await tools["update_user"](5, disabled=True, confirm=True)

    assert "User updated: id=5" in result
    (method, path, kwargs) = [r for r in client.requests if r[1] == "admin/user/update"][0]
    body = kwargs["json"]
    assert body["id"] == 5
    assert body["username"] == "bob"
    assert body["disabled"] is True
    assert body["permission"] == 53247


@pytest.mark.asyncio
async def test_create_user_requires_confirm(admin_tools) -> None:
    tools, client = admin_tools

    result = await tools["create_user"]("alice", confirm=False)

    assert "confirm=true" in result
    assert client.requests == []
