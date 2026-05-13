import io

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openai import AsyncOpenAI

from app.config import get_settings
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/transcribe", tags=["transcribe"])


@router.post("")
async def transcribe(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> dict[str, str]:
    settings = get_settings()
    key = settings.openai_key_effective()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="apps/api/.env mein OPENAI_API_KEY ya OUTSPARK_OPENAI_STAGING_API_KEY set karo (Whisper ke liye).",
        )
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    timeout = httpx.Timeout(connect=30.0, read=120.0, write=60.0, pool=30.0)
    client = AsyncOpenAI(api_key=key, timeout=timeout)
    buf = io.BytesIO(raw)
    buf.name = file.filename or "audio.webm"
    try:
        tr = await client.audio.transcriptions.create(model="whisper-1", file=buf)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Transcription failed: {e!s}",
        ) from e
    return {"text": getattr(tr, "text", "") or ""}
