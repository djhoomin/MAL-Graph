from http.cookies import SimpleCookie

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from .. import agent, auth, db, ingest, users
from ..config import settings
from . import auth_routes
from .routes import router


class UserMiddleware:
    """Bind the signed-in MAL user for the duration of a request (see users.current_username).

    With sign-in configured (PUBLIC_URL set) the user comes only from the session cookie, and a visitor who has not
    signed in has no user. Without it, as in local development, every request belongs to MAL_USERNAME.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        username: str | None = None  # None falls back to MAL_USERNAME
        if settings.sign_in:
            raw = dict(scope.get("headers") or []).get(b"cookie", b"").decode("latin-1")
            jar = SimpleCookie()
            try:
                jar.load(raw)
            except Exception:
                pass
            morsel = jar.get(auth.SESSION_COOKIE)
            username = auth.session_user(morsel.value if morsel else None) or ""  # "" means nobody
        with users.use_user(username):
            await self.app(scope, receive, send)


app = FastAPI(title="MAL-Graph API", version="0.1.0")
app.add_middleware(UserMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(auth_routes.router)


@app.on_event("startup")
def _startup() -> None:
    db.ensure_schema()
    ingest.drop_legacy_user_props()
    agent.migrate_conversations()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
