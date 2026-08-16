"""Behavior tests for task MCP tools."""

import pytest


@pytest.mark.asyncio
async def test_list_tasks_uses_typed_task_endpoint(task_tools) -> None:
    tools, client = task_tools

    result = await tools["list_tasks"](
        task_type="offline_download",
        status="done",
        page=2,
        per_page=25,
    )

    assert result == "{}"
    assert client.requests == [
        (
            "GET",
            "task/offline_download/done",
            {"params": {"page": 2, "per_page": 25}},
        )
    ]


@pytest.mark.asyncio
async def test_list_tasks_all_queries_all_categories(task_tools) -> None:
    tools, client = task_tools
    from openlist_mcp.tools.task import TASK_TYPES

    result = await tools["list_tasks"](task_type="all", status="undone")

    expected = [
        ("GET", f"task/{t}/undone", {"params": {"page": 1, "per_page": 50}})
        for t in sorted(TASK_TYPES)
    ]
    assert client.requests == expected
    assert '"task_type": "all"' in result
    assert '"results"' in result
    assert '"total"' in result


@pytest.mark.asyncio
async def test_get_task_info_uses_tid_query_param(task_tools) -> None:
    tools, client = task_tools

    result = await tools["get_task_info"]("task-123", task_type="offline_download")

    assert result == "{}"
    assert client.requests == [
        (
            "POST",
            "task/offline_download/info",
            {"params": {"tid": "task-123"}},
        )
    ]


@pytest.mark.asyncio
async def test_task_tools_validate_task_type(task_tools) -> None:
    tools, client = task_tools

    with pytest.raises(ValueError, match="Unsupported task_type"):
        await tools["get_task_info"]("task-123", task_type="bad")

    assert client.requests == []


@pytest.mark.asyncio
async def test_cancel_task_uses_typed_endpoint(task_tools) -> None:
    tools, client = task_tools

    result = await tools["cancel_task"](
        "task-123",
        task_type="offline_download",
        confirm=True,
    )

    assert result == "Task cancelled: task-123"
    assert client.requests == [
        (
            "POST",
            "task/offline_download/cancel",
            {"params": {"tid": "task-123"}},
        )
    ]


@pytest.mark.asyncio
async def test_batch_cancel_tasks_sends_array(task_tools) -> None:
    tools, client = task_tools

    result = await tools["batch_cancel_tasks"](
        task_ids=["t1", "t2"],
        task_type="offline_download",
        confirm=True,
    )

    assert "submitted" in result.lower()
    assert client.requests == [
        (
            "POST",
            "task/offline_download/cancel_some",
            {"json": ["t1", "t2"]},
        )
    ]


@pytest.mark.asyncio
async def test_batch_delete_tasks_sends_array(task_tools) -> None:
    tools, client = task_tools

    result = await tools["batch_delete_tasks"](
        task_ids=["t1"],
        task_type="offline_download",
        confirm=True,
    )

    assert "submitted" in result.lower()
    assert client.requests == [
        (
            "POST",
            "task/offline_download/delete_some",
            {"json": ["t1"]},
        )
    ]


@pytest.mark.asyncio
async def test_batch_retry_tasks_sends_array(task_tools) -> None:
    tools, client = task_tools

    result = await tools["batch_retry_tasks"](
        task_ids=["t1", "t2", "t3"],
        task_type="offline_download",
    )

    assert "submitted" in result.lower()
    assert client.requests == [
        (
            "POST",
            "task/offline_download/retry_some",
            {"json": ["t1", "t2", "t3"]},
        )
    ]


@pytest.mark.asyncio
async def test_clear_done_tasks(task_tools) -> None:
    tools, client = task_tools

    result = await tools["clear_done_tasks"](task_type="offline_download")

    assert "cleared" in result.lower()
    assert client.requests == [("POST", "task/offline_download/clear_done", {})]


@pytest.mark.asyncio
async def test_clear_succeeded_tasks(task_tools) -> None:
    tools, client = task_tools

    result = await tools["clear_succeeded_tasks"](task_type="offline_download")

    assert "cleared" in result.lower()
    assert client.requests == [("POST", "task/offline_download/clear_succeeded", {})]


@pytest.mark.asyncio
async def test_retry_failed_tasks(task_tools) -> None:
    tools, client = task_tools

    result = await tools["retry_failed_tasks"](task_type="offline_download")

    assert "retry" in result.lower()
    assert client.requests == [("POST", "task/offline_download/retry_failed", {})]


@pytest.mark.asyncio
async def test_batch_tasks_require_confirm(task_tools) -> None:
    tools, client = task_tools

    result = await tools["batch_cancel_tasks"](task_ids=["t1"], confirm=False)
    assert "not performed" in result.lower()
    assert client.requests == []


@pytest.mark.asyncio
async def test_batch_tasks_require_nonempty_ids(task_tools) -> None:
    tools, client = task_tools

    result = await tools["batch_cancel_tasks"](task_ids=[], confirm=True)
    assert "no task" in result.lower()
    assert client.requests == []

    result = await tools["batch_delete_tasks"](task_ids=[], confirm=True)
    assert "no task" in result.lower()

    result = await tools["batch_retry_tasks"](task_ids=[], task_type="offline_download")
    assert "no task" in result.lower()
