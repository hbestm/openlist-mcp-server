# OpenList API Compatibility Notes

This MCP server calls OpenList's HTTP API through `OpenListClient`. Most tools are
thin wrappers over the matching OpenList endpoint, with input validation and optional
MCP-side safety controls.

Compatibility was verified against OpenList **v4.2.2**, **v4.2.5**, **v4.2.6
(2bdf16d)**, and current `master` (post-v4.2.5). See [CHANGELOG.md](../CHANGELOG.md)
for version history.

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
string** (OpenList reads `c.Query("id")` — verified in v4.2.2, v4.2.5, v4.2.6, and
master). The MCP tools `delete_share`, `enable_share`, `disable_share`, and
`cancel_share` therefore send `params={"id": ...}`, not a JSON body.

`create_share` / `update_share` use a JSON body (`files`, `pwd`, `expires`,
`max_accessed`, `remark`, `id`).

## Metadata APIs — update rewrites the whole record, delete reads a query param

`create_meta` / `update_meta` / `delete_meta` wrap the directory-metadata
endpoints (verified against v4.2.6):

- `POST /api/admin/meta/create` — JSON body is the whole `model.Meta`. Only
  `path` is required; the rest are `password`, `p_sub`, `hide`, `h_sub`,
  `write`, `w_sub`, `readme`, `r_sub`, `header`, `header_sub`, `read_users`,
  `read_users_sub`, `write_users`, `write_users_sub`. `None` is not sent, so a
  field the caller omitted keeps the server default.
- `POST /api/admin/meta/update` — JSON body is the **whole record including
  `id`**, and the handler writes every column. An update carrying only the
  changed fields therefore zeroes everything else, so `update_meta` reads the
  entry first and merges. A field sent as `""` or `[]` is a real value — that is
  how a password or an ACL is cleared.
- `POST /api/admin/meta/delete` — id via `?id=` **query string**
  (`c.Query("id")`), the same shape as the share delete endpoints.
- `GET /api/admin/meta/get` — id via `?id=` query string.

`hide` is validated server-side as a regex; an invalid pattern is rejected with
400 before anything is stored.

## Resumable multipart upload (OpenList v4.2.5+)

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

The endpoints ship in **v4.2.5 and later** (verified live on v4.2.5 and v4.2.6)
and are gated by the `multipart_enabled` admin setting; older v4.2.x builds
answer 403 "multipart upload is disabled". Empty files are not supported by
the multipart API — use `upload_file` / `upload_local_file`.

## Other wrapped endpoints

- `POST /api/fs/get_direct_upload_info` — client-side direct upload info
  (`path`, `file_name`, `file_size`, optional `tool`). v4.2.6 added its own
  write-permission and mount checks to the handler.
- `POST /api/admin/scan/start` (`path`, optional `limit`),
  `POST /api/admin/scan/stop`, `GET /api/admin/scan/progress` — manual scan.
- Admin write groups, verified live against v4.2.6: storage CRUD
  (`/api/admin/storage/{create,update,delete,enable,disable,load_all}`), user
  write (`/api/admin/user/{create,update}`, with `delete` and `del_cache` reading
  their id/username from the query string), and the offline-download client
  settings (`/api/admin/setting/set_*`, which save the setting before probing the
  client, so a failed probe still persists the configuration).

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
2. Check whether an update endpoint replaces the whole record or merges: if the
   handler binds the full model and writes every column (as
   `admin/meta/update` does), the tool has to read first and merge, or omitted
   fields get zeroed.
3. Add validation for path, file name, pagination, or destructive confirmation inputs.
4. Add a fake-client unit test that checks request method, path, params, and JSON body.
5. Add or update a live smoke script only when the endpoint can be exercised safely.
6. Document version or deployment caveats here.