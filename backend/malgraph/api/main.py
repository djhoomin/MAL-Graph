import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from .. import db, ingest, users
from .routes import router


MAL_USERNAME = re.compile(r"[A-Za-z0-9_-]{2,16}")


class UserMiddleware:
    """Bind the requesting MAL user for the duration of a request (see users.current_username).

    Until sign-in exists the user is MAL_USERNAME, or whoever an `X-MAL-User` header names. Every MAL list is
    public, so naming another user only shows what MAL already shows. Sign-in will replace the header.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header = dict(scope.get("headers") or []).get(b"x-mal-user", b"").decode(errors="ignore").strip()
        username = header if MAL_USERNAME.fullmatch(header) else None
        with users.use_user(username):
            await self.app(scope, receive, send)


app = FastAPI(title="MAL-Graph API", version="0.1.0")
app.add_middleware(UserMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def _startup() -> None:
    db.ensure_schema()
    ingest.drop_legacy_user_props()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
