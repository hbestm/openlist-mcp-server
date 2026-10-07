# OpenList API Compatibility Notes

This MCP server calls OpenList's HTTP API through `OpenListClient`. Most tools are
thin wrappers over the matching OpenList endpoint, with input validation and optional
MCP-side safety controls.

Compatibility was verified against OpenList **v4.2.2**, **v4.2.5**, and current
`master` (post-v4.2.5). See [CHANGELOG.md](../CHANGELOG.md) for version history.

## Task APIs (typed per task category)

`GET /api/task/{task_type}/{status}` lists tasks (`done` / `undone`), and the
following POST endpoints operate on a single task via `?tid=` (query string):

- `POST /api/task/{task_type}/info?tid=...` — `get_task_info`
- `POST /api/task/{task_type}/retry?tid=...` — `retry_task`
- `POST /api/task/{task_type}/cancel?tid=...` — `cancel_task`
- `POST /api/task/{task_type}/delete?tid=...` — `delete_task`
- `POST /api/task/{task_type}/cancel_some` / `delete_some` / `retry_some` —
  batch operations (JSON body is the task id list)
- `POST /api/task/{task_type}/clear_done` / `clear_succeeded` / `retry_failed`

Supported task types (all registered by OpenList):

- `upload`
- `copy`
- `move`
- `offline_download`
- `offline_download_transfer`
- `decompress`
- `decompress_upload`

Supported list statuses are `done` and `undone`.

## Share APIs — id is a query parameter

`POST /api/share/delete`, `POST /api/share/enable` and
`POST /api/share/disable` identify the share with `?id=` **in the query
string** (OpenList reads `c.Query("id")` — verified in v4.2.2, v4.2.5, and
master). The MCP tools `delete_share`, `enable_share`, `disable_share`, and
`cancel_share` therefore send `params={"id": ...}`, not a JSON body.

`create_share` / `update_share` use a JSON body (`files`, `pwd`, `expires`,
`max_accessed`, `remark`, `id`).

## Resumable multipart upload (OpenList master, post-v4.2.5)

New endpoints wrapped by the `upload_file_multipart` /
`multipart_upload_local_file` / `multipart_upload_status` /
`multipart_abort_upload` tools:

- `POST /api/fs/multipart/init` — headers `File-Path`, `X-File-Size` (required),
  `X-Chunk-Size`, `Overwrite`, `X-File-Md5`; returns a session snapshot.
- `PUT /api/fs/multipart/chunk` — headers `X-Upload-Id`, `X-Chunk-Index`;
  body is the raw chunk bytes. Chunks are idempotent and may arrive
  concurrently/out of order.
- `POST /api/fs/multipart/complete` — header `X-Upload-Id`.
- `GET /api/fs/multipart/status` — `?upload_id=` or `?path=&size=`.
- `POST /api/fs/multipart/abort` — header `X-Upload-Id`.

This API is gated by the `multipart_enabled` admin setting and requires an
OpenList build that includes it (master after v4.2.5). Empty files are not
supported by the multipart API — use `upload_file` / `upload_local_file`.

## Other wrapped endpoints

- `POST /api/fs/get_direct_upload_info` — client-side direct upload info
  (`path`, `file_name`, `file_size`, optional `tool`).
- `POST /api/admin/scan/start` (`path`, optional `limit`),
  `POST /api/admin/scan/stop`, `GET /api/admin/scan/progress` — manual scan.

## HTML task responses

If a task list call returns HTML instead of JSON, the target OpenList deployment is
serving a web page or fallback route for that API path. In that case:

- `get_task_info` may still work when the caller has a known task id.
- `list_tasks` returns a structured compatibility error instead of leaking raw HTML.
- The deployment should be checked against its OpenList version, reverse proxy rules,
  and enabled task features.

## Compatibility expectations

The unit tests assert request shapes for the endpoints this project wraps. Live
compatibility still depends on the target OpenList server because storage drivers,
admin permissions, offline download providers, and task endpoints can differ by
deployment.

When adding a new tool:

1. Confirm the endpoint exists in the current OpenList API (check
   `server/router.go` and the handler's request binding — query param vs JSON body).
2. Add validation for path, file name, pagination, or destructive confirmation inputs.
3. Add a fake-client unit test that checks request method, path, params, and JSON body.
4. Add or update a live smoke script only when the endpoint can be exercised safely.
5. Document version or deployment caveats here.