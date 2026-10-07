"""OpenList API client with JWT authentication management."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any

import httpx

from .config import get_config

logger = logging.getLogger(__name__)


def _generate_totp(secret: str) -> str:
    """Generate a TOTP code from the given secret using pyotp."""
    import pyotp

    totp = pyotp.TOTP(secret)
    return str(totp.now())


class OpenListError(Exception):
    """Error from OpenList API."""

    def __init__(self, message: str, code: int = 500):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class OpenList2FAError(OpenListError):
    """Login requires a 2FA (TOTP) code."""

    def __init__(self, message: str = "2FA code is required"):
        super().__init__(message, code=402)


class OpenListClient:
    """Async HTTP client for OpenList REST API with automatic JWT token management."""

    def __init__(self) -> None:
        self._config = get_config()
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._2fa_cached: bool = False

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._config.api_base,
                timeout=httpx.Timeout(120.0, connect=10.0, write=120.0),
                follow_redirects=True,
            )
        return self._client

    @property
    def _headers(self) -> dict[str, str]:
        """Build request headers with JWT token.

        OpenList uses token directly in Authorization header (not Bearer format).
        """
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = self._token
        return headers

    def _parse_response(self, resp: httpx.Response, action: str = "Request") -> dict[str, Any]:
        """Parse an OpenList JSON response and raise friendly errors."""
        text_preview = resp.text[:300].replace("\n", " ").strip()
        if resp.status_code < 200 or resp.status_code >= 300:
            raise OpenListError(
                f"{action} failed with HTTP {resp.status_code}: {text_preview}",
                code=resp.status_code,
            )
        try:
            data = resp.json()
        except ValueError as exc:
            if text_preview.lower().startswith("<!doctype html") or "<html" in text_preview.lower():
                raise OpenListError(
                    f"{action} returned HTML instead of JSON. "
                    "This endpoint may be unavailable in your OpenList version or deployment.",
                    code=resp.status_code,
                ) from exc
            raise OpenListError(
                f"{action} returned non-JSON response: {text_preview}",
                code=resp.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise OpenListError(f"{action} returned unexpected response type", code=500)
        return data

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid JWT token. Login if needed."""
        if self._token:
            return
        if self._2fa_cached and not self._config.has_totp_secret:
            raise OpenList2FAError(
                "2FA is enabled on this OpenList account. "
                "Call the login tool with the otp_code parameter to authenticate."
            )
        async with self._lock:
            if self._token:
                return
            if self._2fa_cached and not self._config.has_totp_secret:
                raise OpenList2FAError(
                    "2FA is enabled on this OpenList account. "
                    "Call the login tool with the otp_code parameter to authenticate."
                )
            try:
                otp_code = (
                    _generate_totp(self._config.totp_secret)
                    if self._config.has_totp_secret
                    else None
                )
                await self.login(otp_code=otp_code)
            except OpenList2FAError:
                self._2fa_cached = True
                if self._config.has_totp_secret:
                    raise OpenListError(
                        "Auto-generated TOTP code was rejected. "
                        "Check your OPENLIST_TOTP_SECRET value.",
                        code=402,
                    ) from None
                raise OpenList2FAError(
                    "2FA is enabled on this OpenList account. "
                    "Call the login tool with the otp_code parameter to authenticate."
                ) from None

    async def login(self, otp_code: str | None = None) -> dict[str, Any]:
        """Login to OpenList and store JWT token.

        Args:
            otp_code: TOTP code for 2FA. Required if the user has enabled
                      two-factor authentication on their OpenList account.
        """
        if not self._config.is_authenticated:
            raise OpenListError(
                "OPENLIST_USERNAME and OPENLIST_PASSWORD are required for authentication.",
                code=401,
            )

        body: dict[str, str] = {
            "username": self._config.username,
            "password": self._config.password,
        }
        if otp_code:
            body["otp_code"] = otp_code

        client = await self._get_client()
        try:
            resp = await client.post("/auth/login", json=body)
        except httpx.HTTPError as exc:
            raise OpenListError(f"Login request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, "Login")
        code: int = data.get("code", 500)
        if code != 200:
            # 2FA code required or invalid
            if code == 402:
                if otp_code:
                    raise OpenListError(
                        "Invalid 2FA code. Please re-run login with a valid TOTP code.",
                        code=402,
                    )
                raise OpenList2FAError()
            raise OpenListError(
                data.get("message", "Login failed"),
                code=code,
            )

        result_data = data.get("data", {})
        if not isinstance(result_data, dict):
            raise OpenListError("Login returned unexpected data format", code=500)
        token = result_data.get("token")
        if not token:
            raise OpenListError("Login succeeded but no token was returned", code=500)
        self._token = token
        self._2fa_cached = False
        logger.info("Login successful")
        return result_data

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        require_auth: bool = True,
        retry_on_busy: bool = True,
    ) -> dict[str, Any]:
        """Make an API request to OpenList.

        Args:
            retry_on_busy: If True (default), automatically retry up to 3 times
                          on SQLITE_BUSY errors with exponential backoff.
        """
        max_retries = 3 if retry_on_busy else 1

        if require_auth:
            await self.ensure_authenticated()

        for attempt in range(1, max_retries + 1):
            client = await self._get_client()
            try:
                resp = await client.request(
                    method,
                    f"/{path.lstrip('/')}",
                    json=json,
                    params=params,
                    headers=self._headers,
                )
            except httpx.HTTPError as exc:
                if attempt < max_retries:
                    await asyncio.sleep(attempt * 2)
                    continue
                raise OpenListError(f"Request failed: {exc}", code=503) from exc

            data = self._parse_response(resp, f"{method.upper()} {path}")

            # Retry on SQLITE_BUSY with exponential backoff
            if (
                data.get("code") == 500
                and isinstance(data.get("message"), str)
                and "SQLITE_BUSY" in data["message"]
                and attempt < max_retries
            ):
                wait = attempt * 2
                logger.warning(
                    "SQLITE_BUSY on %s %s, retry %d/%d in %ds",
                    method.upper(),
                    path,
                    attempt,
                    max_retries,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            if data.get("code") != 200:
                if data.get("code") == 401 and self._token and require_auth:
                    self._token = None
                    await self.ensure_authenticated()
                    try:
                        resp = await client.request(
                            method,
                            f"/{path.lstrip('/')}",
                            json=json,
                            params=params,
                            headers=self._headers,
                        )
                    except httpx.HTTPError as exc:
                        raise OpenListError(f"Request retry failed: {exc}", code=503) from exc
                    data = self._parse_response(resp, f"{method.upper()} {path} retry")
                    if data.get("code") != 200:
                        self._token = None
                        raise OpenListError(
                            data.get("message", "Request failed"),
                            code=data.get("code", 500),
                        )
                else:
                    raise OpenListError(
                        data.get("message", "Request failed"), code=data.get("code", 500)
                    )

            result = data.get("data", {})
            return result if isinstance(result, dict) else {"value": result}

        raise OpenListError("Max retries exceeded for SQLITE_BUSY", code=500)

    async def upload(
        self,
        path: str,
        file_content: bytes | AsyncIterable[bytes],
        file_name: str,
        as_task: bool = True,
    ) -> dict[str, Any]:
        """Upload a file to OpenList."""
        await self.ensure_authenticated()
        client = await self._get_client()

        url = "/fs/put"
        if as_task:
            url += "?as_task=true"

        target_path = f"{path.rstrip('/')}/{file_name}" if path != "/" else f"/{file_name}"
        try:
            resp = await client.put(
                url,
                content=file_content,
                headers={
                    "Authorization": self._token or "",
                    "File-Path": target_path,
                    "Content-Type": "application/octet-stream",
                },
            )
        except httpx.HTTPError as exc:
            raise OpenListError(f"Upload request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, "Upload")
        if data.get("code") != 200:
            raise OpenListError(data.get("message", "Upload failed"), code=data.get("code", 500))

        result = data.get("data", {})
        return result if isinstance(result, dict) else {"value": result}

    async def multipart_form(
        self,
        path: str,
        field_name: str,
        file_bytes: bytes,
        file_name: str,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Send a multipart form-data POST request to OpenList.

        Used for endpoints like torrent upload that accept file uploads
        via multipart form rather than JSON body.

        Args:
            path: API path (e.g. "fs/torrent/upload_parse").
            field_name: The form field name for the file.
            file_bytes: Raw file content bytes.
            file_name: Display filename for the form.
            content_type: MIME type of the file content.

        Returns:
            Parsed JSON data dict from the response.
        """
        await self.ensure_authenticated()
        client = await self._get_client()

        files = {field_name: (file_name, file_bytes, content_type)}
        try:
            resp = await client.post(
                f"/{path.lstrip('/')}",
                files=files,
                headers={"Authorization": self._token or ""},
            )
        except httpx.HTTPError as exc:
            raise OpenListError(f"Multipart upload request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, f"POST {path}")
        if data.get("code") != 200:
            raise OpenListError(
                data.get("message", "Multipart upload failed"),
                code=data.get("code", 500),
            )

        result = data.get("data", {})
        return result if isinstance(result, dict) else {"value": result}

    async def multipart_init(
        self,
        file_path: str,
        file_size: int,
        chunk_size: int | None = None,
        overwrite: bool = True,
        file_md5: str | None = None,
    ) -> dict[str, Any]:
        """Start (or resume) a resumable multipart upload session.

        Requires an OpenList build with the ``/fs/multipart`` API (post-v4.2.5
        master) and the ``multipart_enabled`` admin setting turned on.
        """
        await self.ensure_authenticated()
        client = await self._get_client()

        headers = {
            "Authorization": self._token or "",
            "File-Path": file_path,
            "X-File-Size": str(file_size),
        }
        if chunk_size and chunk_size > 0:
            headers["X-Chunk-Size"] = str(chunk_size)
        if not overwrite:
            headers["Overwrite"] = "false"
        if file_md5:
            headers["X-File-Md5"] = file_md5

        try:
            resp = await client.post("/fs/multipart/init", headers=headers)
        except httpx.HTTPError as exc:
            raise OpenListError(f"Multipart init request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, "Multipart init")
        if data.get("code") != 200:
            raise OpenListError(
                data.get("message", "Multipart init failed"), code=data.get("code", 500)
            )
        result = data.get("data", {})
        return result if isinstance(result, dict) else {}

    async def multipart_chunk(self, upload_id: str, index: int, chunk: bytes) -> dict[str, Any]:
        """Upload one chunk of a multipart session.

        Chunks are idempotent; ``index`` is zero-based. Only the session owner
        may send chunks.
        """
        await self.ensure_authenticated()
        client = await self._get_client()
        try:
            resp = await client.put(
                "/fs/multipart/chunk",
                content=chunk,
                headers={
                    "Authorization": self._token or "",
                    "X-Upload-Id": upload_id,
                    "X-Chunk-Index": str(index),
                    "Content-Type": "application/octet-stream",
                },
            )
        except httpx.HTTPError as exc:
            raise OpenListError(f"Multipart chunk request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, f"Multipart chunk {index}")
        if data.get("code") != 200:
            raise OpenListError(
                data.get("message", f"Multipart chunk {index} failed"),
                code=data.get("code", 500),
            )
        result = data.get("data", {})
        return result if isinstance(result, dict) else {}

    async def multipart_complete(self, upload_id: str) -> dict[str, Any]:
        """Finalize a multipart upload session and persist the file."""
        await self.ensure_authenticated()
        client = await self._get_client()
        try:
            resp = await client.post(
                "/fs/multipart/complete",
                headers={"Authorization": self._token or "", "X-Upload-Id": upload_id},
            )
        except httpx.HTTPError as exc:
            raise OpenListError(f"Multipart complete request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, "Multipart complete")
        if data.get("code") != 200:
            raise OpenListError(
                data.get("message", "Multipart complete failed"), code=data.get("code", 500)
            )
        result = data.get("data", {})
        return result if isinstance(result, dict) else {}

    async def multipart_status(
        self, upload_id: str = "", path: str = "", file_size: int = 0
    ) -> dict[str, Any]:
        """Query a multipart session by upload_id, or by path+size."""
        await self.ensure_authenticated()
        client = await self._get_client()
        params: dict[str, Any] = {}
        if upload_id:
            params["upload_id"] = upload_id
        elif path and file_size > 0:
            params["path"] = path
            params["size"] = file_size
        else:
            raise ValueError("multipart_status requires upload_id, or path and file_size")
        try:
            resp = await client.get("/fs/multipart/status", params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise OpenListError(f"Multipart status request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, "Multipart status")
        if data.get("code") != 200:
            raise OpenListError(
                data.get("message", "Multipart status failed"), code=data.get("code", 500)
            )
        result = data.get("data", {})
        return result if isinstance(result, dict) else {}

    async def multipart_abort(self, upload_id: str) -> dict[str, Any]:
        """Abort a multipart upload session and discard its chunks."""
        await self.ensure_authenticated()
        client = await self._get_client()
        try:
            resp = await client.post(
                "/fs/multipart/abort",
                headers={"Authorization": self._token or "", "X-Upload-Id": upload_id},
            )
        except httpx.HTTPError as exc:
            raise OpenListError(f"Multipart abort request failed: {exc}", code=503) from exc

        data = self._parse_response(resp, "Multipart abort")
        if data.get("code") != 200:
            raise OpenListError(
                data.get("message", "Multipart abort failed"), code=data.get("code", 500)
            )
        result = data.get("data", {})
        return result if isinstance(result, dict) else {}

    def clear_token(self) -> None:
        """Clear the cached authentication token."""
        self._token = None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


_client: OpenListClient | None = None


async def get_client() -> OpenListClient:
    """Get or create the global OpenList client instance."""
    global _client
    if _client is None:
        _client = OpenListClient()
    return _client
