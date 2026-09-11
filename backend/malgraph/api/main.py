from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import db
from .routes import router

app = FastAPI(title="MAL-Graph API", version="0.1.0")
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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
