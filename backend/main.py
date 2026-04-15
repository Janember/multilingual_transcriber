"""
backend/main.py  (code-switching aware + full error logging)
"""

import asyncio
import json
import tempfile
import os
import traceback

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from transcriber import WhisperTranscriber
from summarizer  import Summarizer
from jargon      import JargonDetector
from session     import TranscriptSession

app = FastAPI(title="MeetScribe API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

transcriber = WhisperTranscriber(model_size="medium")
summarizer  = Summarizer()
jargon_det  = JargonDetector()
session     = TranscriptSession()

SUPPORTED_LANGS = {
    "auto": None,
    "en":   "english",
    "tl":   "tagalog",
    "ceb":  "cebuano",
}


@app.websocket("/ws/audio")
async def audio_ws(websocket: WebSocket, lang: str = "auto"):
    await websocket.accept()
    whisper_lang = SUPPORTED_LANGS.get(lang)
    print(f"[WS] Client connected – language: {lang}")

    try:
        while True:
            # ── Receive audio chunk ───────────────────────
            try:
                audio_bytes = await websocket.receive_bytes()
                print(f"[WS] Received chunk: {len(audio_bytes)} bytes")
            except WebSocketDisconnect:
                raise
            except Exception as e:
                print(f"[WS] Error receiving bytes: {e}")
                break

            # ── Write to temp file ────────────────────────
            try:
                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
                    tmp.write(audio_bytes)
                    tmp_path = tmp.name
                print(f"[WS] Wrote temp file: {tmp_path}")
            except Exception as e:
                print(f"[WS] Error writing temp file: {e}")
                continue

            # ── Transcribe ────────────────────────────────
            try:
                result = await asyncio.to_thread(
                    transcriber.transcribe, tmp_path, language=whisper_lang
                )
                print(f"[WS] Transcription result: '{result['text'][:80]}' "
                      f"lang={result.get('language')} cs={result.get('code_switched')}")
            except Exception as e:
                print(f"[WS] Transcription error: {e}")
                traceback.print_exc()
                continue
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

            if not result["text"].strip():
                print("[WS] Empty transcription — skipping")
                continue

            # ── Jargon detection ──────────────────────────
            try:
                flagged = jargon_det.detect(result["text"], result.get("segments", []))
            except Exception as e:
                print(f"[WS] Jargon detection error: {e}")
                flagged = []

            # ── Store in session ──────────────────────────
            try:
                entry = session.append(
                    text=result["text"],
                    language=result.get("language", lang),
                    jargon=flagged,
                    segments=result.get("segments", []),
                    code_switched=result.get("code_switched", False),
                )
            except Exception as e:
                print(f"[WS] Session append error: {e}")
                traceback.print_exc()
                continue

            # ── Send result back to extension ─────────────
            try:
                await websocket.send_text(json.dumps(entry))
            except Exception as e:
                print(f"[WS] Send error: {e}")
                break

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")
        traceback.print_exc()


@app.get("/session")
def get_session():
    return session.to_dict()


@app.post("/session/reset")
def reset_session():
    session.reset()
    return {"status": "reset"}


@app.post("/summarize")
async def summarize_now():
    full_text = session.full_text()
    if not full_text.strip():
        raise HTTPException(status_code=400, detail="No transcript yet.")
    notes = await asyncio.to_thread(summarizer.summarize, full_text)
    session.set_notes(notes)
    return {"notes": notes}


@app.get("/jargon")
def get_jargon():
    return {"jargon": session.all_jargon()}


@app.get("/export")
def export_session(fmt: str = "json"):
    if fmt == "json":
        return session.to_dict()
    elif fmt == "txt":
        return {"content": session.to_txt()}
    elif fmt == "markdown":
        return {"content": session.to_markdown()}
    raise HTTPException(status_code=400, detail="fmt must be json | txt | markdown")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)