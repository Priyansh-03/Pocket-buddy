from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, chat, expenses, health, transcribe, users

app = FastAPI(title="AI Financial Survival Assistant API")

_settings = get_settings()
_origins = [o.strip() for o in _settings.cors_origin.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins else ["*"],
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
