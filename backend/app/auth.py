"""Optional HTTP Basic auth for the whole app (HTTP and WebSocket).

Set APP_PASSWORD to turn it on. The username is ignored. /api/health stays open for the host's
health check. Not set = no auth, which is fine for local use. Same-origin only: use it with the
single-service Render deploy, where the browser reuses the Basic credentials for /api and the WebSocket.
"""

import base64
import os
import secrets

OPEN_PATHS = {"/api/health"}


class BasicAuthMiddleware:
    def __init__(self, app, password: str):
        self.app = app
        self.password = password

    def _authorized(self, scope) -> bool:
        for key, value in scope.get("headers", []):
            if key == b"authorization" and value[:6].lower() == b"basic ":
                try:
                    _, _, supplied = base64.b64decode(value[6:]).decode().partition(":")
                except Exception:
                    return False
                return secrets.compare_digest(supplied.encode(), self.password.encode())
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or scope["path"] in OPEN_PATHS:
            return await self.app(scope, receive, send)
        if scope["type"] == "http" and scope["method"] == "OPTIONS":  # CORS preflight
            return await self.app(scope, receive, send)
        if self._authorized(scope):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"www-authenticate", b'Basic realm="Voice Form Tester"'), (b"content-length", b"12")]})
        await send({"type": "http.response.body", "body": b"Unauthorized"})


def app_password() -> str:
    return os.getenv("APP_PASSWORD", "")
