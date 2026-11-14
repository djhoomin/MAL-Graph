from http.cookies import SimpleCookie

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from .. import agent, auth, db, genders, ingest, users
from ..config import settings
from . import auth_routes, game_routes, golf_routes, kmk_routes
from .ratelimit import RateLimitMiddleware
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
# Starlette runs the last-added middleware first, so the limiter (added first) sees the user UserMiddleware sets.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(UserMiddleware)
if not settings.public_url.startswith("https://"):
    # Local development only: lets a UI on another port call the API directly. In production the UI and the API
    # share one origin behind Caddy, so no cross-origin access is allowed at all.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(router)
app.include_router(auth_routes.router)
app.include_router(golf_routes.router)
app.include_router(kmk_routes.router)
app.include_router(game_routes.router)


@app.on_event("startup")
def _startup() -> None:
    db.ensure_schema()
    ingest.drop_legacy_user_props()
    agent.migrate_conversations()
    agent.guard_self_test()
    if settings.genders_worker:
        genders.start()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
