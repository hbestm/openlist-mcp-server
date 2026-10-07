"""Task management tools for OpenList MCP Server."""

from __future__ import annotations

import asyncio
import json
import logging

from mcp.server.mcpserver import MCPServer as FastMCP

from ..client import get_client
from . import enforce_writable, validate_pagination

logger = logging.getLogger(__name__)

TASK_TYPES = {
    "upload",
    "copy",
    "offline_download",
    "offline_download_transfer",
    "decompress",
    "decompress_upload",
}

# Sentinel value to query all task types and merge results.
_ALL_TASK_TYPES = "all"

TASK_LIST_STATUSES = {"done", "undone"}


def _validate_task_type(task_type: str) -> str:
    task_type = task_type.strip()
    if task_type != _ALL_TASK_TYPES and task_type not in TASK_TYPES:
        raise ValueError(
            f"Unsupported task_type: {task_type}. "
            f"Supported values: {', '.join(sorted(TASK_TYPES))} or '{_ALL_TASK_TYPES}' (all)"
        )
    return task_type


def _task_params(task_id: str) -> dict[str, str]:
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("task_id must not be empty")
    return {"tid": task_id}


def register_task_tools(mcp: FastMCP) -> None:
    """Register task management MCP tools."""

    @mcp.tool()
    async def list_tasks(
        task_type: str = "offline_download",
        status: str = "undone",
        page: int = 1,
        per_page: int = 50,
    ) -> str:
        """List asynchronous tasks by OpenList task type and status.

        OpenList v4 exposes task APIs as `/api/task/{task_type}/{status}`.
        Common task types include offline_download, upload, copy, and decompress.
        Use task_type="all" to query all task categories simultaneously.

        Args:
            task_type: Task category: offline_download, upload, copy, decompress,
                       offline_download_transfer, decompress_upload, or "all" (all types).
            status: Task list status: "undone" for running/pending or "done" for completed.
            page: Page number for deployments that support pagination.
            per_page: Page size for deployments that support pagination.

        Returns:
            JSON string with task list data. When task_type="all", results from
            all categories are merged with a "task_type" label on each entry.
        """

        task_type = _validate_task_type(task_type)
        status = status.strip()
        if status not in TASK_LIST_STATUSES:
            raise ValueError(
                f"Unsupported status: {status}. "
                f"Supported values: {', '.join(sorted(TASK_LIST_STATUSES))}"
            )
        validate_pagination(page, per_page)
        client = await get_client()

        if task_type == _ALL_TASK_TYPES:
            # Query all categories concurrently
            async def _fetch_one(t: str) -> dict:
                try:
                    data = await client.request(
                        "GET",
                        f"task/{t}/{status}",
                        params={"page": page, "per_page": per_page},
                    )
                except Exception as exc:
                    logger.warning("list_tasks(all): %s returned error: %s", t, exc)
                    return {"task_type": t, "error": str(exc), "tasks": []}
                tasks = data.get("value", data.get("tasks", data))
                if isinstance(tasks, dict):
                    tasks = [tasks]
                if not isinstance(tasks, list):
                    tasks = []
                for task_entry in tasks:
                    if isinstance(task_entry, dict):
                        task_entry["_task_type"] = t
                return {"task_type": t, "tasks": tasks}

            results = await asyncio.gather(*[_fetch_one(t) for t in sorted(TASK_TYPES)])
            return json.dumps(
                {
                    "task_type": "all",
                    "results": results,
                    "total": sum(len(r["tasks"]) for r in results),
                },
                indent=2,
                ensure_ascii=False,
            )

        # Single task type
        data = await client.request(
            "GET",
            f"task/{task_type}/{status}",
            params={"page": page, "per_page": per_page},
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def get_task_info(
        task_id: str,
        task_type: str = "offline_download",
    ) -> str:
        """Get one task by ID using OpenList's typed task API.

        Args:
            task_id: The task ID returned by OpenList.
            task_type: Task category, e.g. offline_download, upload, copy.

        Returns:
            JSON string with task details.
        """
        task_type = _validate_task_type(task_type)
        client = await get_client()
        data = await client.request(
            "POST",
            f"task/{task_type}/info",
            params=_task_params(task_id),
        )
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def delete_task(
        task_id: str,
        task_type: str = "offline_download",
        confirm: bool = False,
    ) -> str:
        """Delete a completed or failed task.

        Args:
            task_id: The ID of the task to delete.
            task_type: Task category, e.g. offline_download, upload, copy.
            confirm: Must be true to actually delete the task. Defaults to false.
        """
        if not confirm:
            return "⚠️ Task deletion not performed. Re-run with confirm=true to delete it."
        task_type = _validate_task_type(task_type)
        enforce_writable("delete_task")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/delete",
            params=_task_params(task_id),
        )
        return f"Task deleted successfully: {task_id}"

    @mcp.tool()
    async def retry_task(
        task_id: str,
        task_type: str = "offline_download",
    ) -> str:
        """Retry a failed task."""
        task_type = _validate_task_type(task_type)
        enforce_writable("retry_task")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/retry",
            params=_task_params(task_id),
        )
        return f"Task retry submitted: {task_id}"

    @mcp.tool()
    async def cancel_task(
        task_id: str,
        task_type: str = "offline_download",
        confirm: bool = False,
    ) -> str:
        """Cancel a running task.

        Args:
            task_id: The ID of the running task to cancel.
            task_type: Task category, e.g. offline_download, upload, copy.
            confirm: Must be true to actually cancel the task. Defaults to false.
        """
        if not confirm:
            return "⚠️ Task cancellation not performed. Re-run with confirm=true to cancel it."
        task_type = _validate_task_type(task_type)
        enforce_writable("cancel_task")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/cancel",
            params=_task_params(task_id),
        )
        return f"Task cancelled: {task_id}"

    @mcp.tool()
    async def batch_cancel_tasks(
        task_ids: list[str],
        task_type: str = "offline_download",
        confirm: bool = False,
    ) -> str:
        """Cancel multiple running tasks by ID.

        Args:
            task_ids: List of task IDs to cancel.
            task_type: Task category, e.g. offline_download, upload, copy.
            confirm: Must be true to actually cancel. Defaults to false.

        Returns:
            Success or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Batch cancellation not performed. Re-run with confirm=true to cancel."
        if not task_ids:
            return "No task IDs provided."
        task_type = _validate_task_type(task_type)
        enforce_writable("batch_cancel_tasks")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/cancel_some",
            json=task_ids,
        )
        return f"Batch cancel submitted for {len(task_ids)} task(s): {task_ids}"

    @mcp.tool()
    async def batch_delete_tasks(
        task_ids: list[str],
        task_type: str = "offline_download",
        confirm: bool = False,
    ) -> str:
        """Delete multiple completed or failed task records.

        Args:
            task_ids: List of task IDs to delete.
            task_type: Task category, e.g. offline_download, upload, copy.
            confirm: Must be true to actually delete. Defaults to false.

        Returns:
            Success or confirmation-required message.
        """
        if not confirm:
            return "⚠️ Batch deletion not performed. Re-run with confirm=true to delete."
        if not task_ids:
            return "No task IDs provided."
        task_type = _validate_task_type(task_type)
        enforce_writable("batch_delete_tasks")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/delete_some",
            json=task_ids,
        )
        return f"Batch delete submitted for {len(task_ids)} task(s): {task_ids}"

    @mcp.tool()
    async def batch_retry_tasks(
        task_ids: list[str],
        task_type: str = "offline_download",
    ) -> str:
        """Retry multiple failed tasks by ID.

        Args:
            task_ids: List of task IDs to retry.
            task_type: Task category, e.g. offline_download, upload, copy.

        Returns:
            Success message.
        """
        if not task_ids:
            return "No task IDs provided."
        task_type = _validate_task_type(task_type)
        enforce_writable("batch_retry_tasks")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/retry_some",
            json=task_ids,
        )
        return f"Batch retry submitted for {len(task_ids)} task(s): {task_ids}"

    @mcp.tool()
    async def clear_done_tasks(
        task_type: str = "offline_download",
    ) -> str:
        """Clear all completed, failed, and cancelled tasks of the given type.

        Removes all tasks that are in a terminal state (succeeded, failed, cancelled).
        Useful for cleaning up task history.

        Args:
            task_type: Task category, e.g. offline_download, upload, copy.

        Returns:
            Success message.
        """
        task_type = _validate_task_type(task_type)
        enforce_writable("clear_done_tasks")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/clear_done",
        )
        return f"Cleared all done/failed/cancelled tasks of type: {task_type}"

    @mcp.tool()
    async def clear_succeeded_tasks(
        task_type: str = "offline_download",
    ) -> str:
        """Clear only successfully completed tasks.

        Unlike clear_done_tasks, this keeps failed and cancelled tasks for inspection.

        Args:
            task_type: Task category, e.g. offline_download, upload, copy.

        Returns:
            Success message.
        """
        task_type = _validate_task_type(task_type)
        enforce_writable("clear_succeeded_tasks")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/clear_succeeded",
        )
        return f"Cleared all succeeded tasks of type: {task_type}"

    @mcp.tool()
    async def retry_failed_tasks(
        task_type: str = "offline_download",
    ) -> str:
        """Retry all failed tasks of the given type.

        One-shot retry for every task in failed state.

        Args:
            task_type: Task category, e.g. offline_download, upload, copy.

        Returns:
            Success message.
        """
        task_type = _validate_task_type(task_type)
        enforce_writable("retry_failed_tasks")
        client = await get_client()
        await client.request(
            "POST",
            f"task/{task_type}/retry_failed",
        )
        return f"Retry submitted for all failed tasks of type: {task_type}"
