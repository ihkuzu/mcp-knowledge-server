import hmac

from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuth:
    """Rejects HTTP requests that do not carry the expected bearer token."""

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            given = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(given, self.expected):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"www-authenticate", b"Bearer"), (b"content-type", b"text/plain")],
                    }
                )
                await send({"type": "http.response.body", "body": b"missing or wrong token"})
                return
        await self.app(scope, receive, send)


def build_app(server, token: str | None, host: str = "127.0.0.1") -> ASGIApp:
    # the SDK checks the Host header against DNS rebinding when bound to localhost
    app = server.streamable_http_app(host=host)
    return BearerAuth(app, token) if token else app
