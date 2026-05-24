from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, chat, expenses, health, transcribe, users


def _expand_loopback_origins(origins: list[str]) -> list[str]:
    """Allow both localhost and 127.0.0.1 for the same port (common Vite / browser mismatch)."""
    out: list[str] = []
    for o in origins:
        if not o or o in out:
            continue
        out.append(o)
        if "://localhost" in o:
            alt = o.replace("://localhost", "://127.0.0.1", 1)
            if alt not in out:
                out.append(alt)
        elif "://127.0.0.1" in o:
            alt = o.replace("://127.0.0.1", "://localhost", 1)
            if alt not in out:
                out.append(alt)
    return out


app = FastAPI(title="AI Financial Survival Assistant API")

_settings = get_settings()
_origins = _expand_loopback_origins([o.strip() for o in _settings.cors_origin.split(",") if o.strip()])
if not _origins:
    _origins = _expand_loopback_origins(
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(expenses.router)
app.include_router(chat.router)
app.include_router(transcribe.router)
