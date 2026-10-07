"""Authentication tools for OpenList MCP Server."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer as FastMCP

from ..client import OpenList2FAError, OpenListError, _generate_totp, get_client
from ..config import get_config
from . import enforce_writable


def register_auth_tools(mcp: FastMCP) -> None:
    """Register authentication-related MCP tools."""

    @mcp.tool()
    async def login(otp_code: str = "") -> str:
        """Login to OpenList server using configured credentials.

        If OPENLIST_TOTP_SECRET is configured, the TOTP code will be generated
        automatically and you do not need to provide otp_code.

        If the OpenList account has two-factor authentication (2FA) enabled
        and no OPENLIST_TOTP_SECRET is set, you must provide the TOTP code
        from your authenticator app.

        Args:
            otp_code: TOTP code for 2FA. Leave empty if OPENLIST_TOTP_SECRET
                      is configured or 2FA is not enabled.

        Returns:
            A success message with user info if login is successful.
        """
        config = get_config()
        client = await get_client()
        resolved_otp = otp_code.strip() or None
        if resolved_otp is None and config.has_totp_secret:
            resolved_otp = _generate_totp(config.totp_secret)
        try:
            await client.login(otp_code=resolved_otp)
            return "Login successful. Token acquired."
        except OpenList2FAError:
            if config.has_totp_secret:
                return (
                    "Auto-generated TOTP code was rejected. "
                    "Please check your OPENLIST_TOTP_SECRET value."
                )
            return (
                "2FA is enabled on this OpenList account. "
                "Please re-run login with your TOTP code:\n\n"
                'login(otp_code="123456")'
            )
        except OpenListError as exc:
            return f"Login failed: {exc.message}"


def register_public_tools(mcp: FastMCP) -> None:
    """Register public (no-auth) MCP tools."""

    @mcp.tool()
    async def get_public_settings() -> str:
        """Get public settings of the OpenList server.

        Returns information about what authentication methods are available,
        share settings, and other public configuration.

        Returns:
            JSON string of public settings.
        """
        client = await get_client()
        data = await client.request("GET", "public/settings", require_auth=False)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def list_my_ssh_keys() -> str:
        """List SSH public keys for the current user.

        Useful when the OpenList server uses SFTP/SSH storage backends.

        Returns:
            JSON string with SSH key list.
        """
        client = await get_client()
        data = await client.request("GET", "me/sshkey/list")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def add_ssh_key(title: str, public_key: str) -> str:
        """Add a new SSH public key for the current user.

        Args:
            title: A name/label for the key (e.g. "my-laptop").
            public_key: The SSH public key content (ssh-rsa AAA...).

        Returns:
            Success or error message.
        """
        if not title or not public_key:
            return "Both title and public_key are required."
        enforce_writable("add_ssh_key")
        client = await get_client()
        await client.request(
            "POST",
            "me/sshkey/add",
            json={"title": title, "public_key": public_key},
        )
        return f"SSH public key '{title}' added successfully."

    @mcp.tool()
    async def delete_ssh_key(key_id: int, confirm: bool = False) -> str:
        """Delete an SSH public key by its ID.

        Args:
            key_id: The numeric ID of the SSH key to delete.
            confirm: Must be true to actually delete. Defaults to false.

        Returns:
            Success or error message.
        """
        if not confirm:
            return "⚠️ SSH key deletion not performed. Re-run with confirm=true to delete it."
        enforce_writable("delete_ssh_key")
        client = await get_client()
        await client.request(
            "POST",
            "me/sshkey/delete",
            json={"id": key_id},
        )
        return f"SSH key {key_id} deleted successfully."

    @mcp.tool()
    async def update_current_user(
        password: str = "",
        old_password: str = "",
        base_path: str = "",
    ) -> str:
        """Update the current user's profile (password, base path).

        At least one field must be provided. Changing password requires
        both old_password and password.

        Args:
            password: New password (if changing).
            old_password: Current password (required when changing password).
            base_path: New base path for the user's storage scope.

        Returns:
            Success or error message.
        """
        if not password and not base_path:
            return "Nothing to update. Provide at least one field."
        enforce_writable("update_current_user")
        body = {}
        if password:
            if not old_password:
                return "old_password is required when changing password."
            body["password"] = password
            body["old_password"] = old_password
        if base_path:
            body["base_path"] = base_path
        client = await get_client()
        await client.request("POST", "me/update", json=body)
        msg = []
        if password:
            msg.append("password changed")
        if base_path:
            msg.append(f'base_path set to "{base_path}"')
        return f"Profile updated: {', '.join(msg)}."
