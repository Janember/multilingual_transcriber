# MeetScribe — Multilingual Lecture Transcription System

**Thesis:** An Automated Multilingual Lecture Transcription and Intelligent Note Generation System  
Using Transformer-Based Speech Recognition and Abstractive Text Summarization

---

## Project structure

```
meet_transcriber/
├── chrome_extension/
│   ├── manifest.json       Chrome MV3 manifest
│   ├── background.js       Service worker: tabCapture → WebSocket
│   ├── popup.html          Extension popup UI
│   └── popup.js            Popup logic
│
├── backend/
│   ├── main.py             FastAPI: WebSocket ingestion + REST API
│   ├── transcriber.py      OpenAI Whisper wrapper (EN / TL / CEB)
│   ├── summarizer.py       BART / mT5 abstractive summarizer
│   ├── jargon.py           Low-confidence + OOV word detector
│   └── session.py          In-memory session store
│
├── frontend/
│   └── app.py              Streamlit dashboard
│
├── requirements.txt
└── README.md               (this file)
```

---

## How to set up for testing

### 1. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> Whisper will download the model weights (~140 MB for "base") on first run.

### 2. Start the backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Check it at: http://localhost:8000/docs (Swagger UI)

### 3. Start the Streamlit frontend

```bash
cd frontend
streamlit run app.py --server.port 8501
```

Open: http://localhost:8501

### 4. Load the Chrome extension

1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select the `chrome_extension/` folder
4. Open [Google Meet](https://meet.google.com) and start or join a meeting
5. Click the MeetScribe extension icon
6. Choose language → click **Start transcription**
7. Watch the transcript appear in the Streamlit dashboard

---

## Supported languages

| Code | Language  | Notes |
|------|-----------|-------|
| `en` | English   | Whisper native; best accuracy |
| `tl` | Tagalog   | Whisper supports; good accuracy |
| `ceb` | Cebuano  | Whisper may detect as Tagalog; patched in `transcriber.py` |
| `auto` | Auto-detect | Whisper detects per chunk |

---

## Key design decisions

### Jargon handling
Words are flagged (never removed) when:
- Whisper confidence probability < 0.70 (`low_confidence`)
- The word matches technical patterns: all-caps (PCR), camelCase (mRNA),  
  hyphenated (co-factor), very long (phosphorylation) (`possible_jargon`)

Flagged words appear in the **Jargon panel** in Streamlit. The full transcript is preserved unchanged.

### Audio chunking
The Chrome extension uses `MediaRecorder` to produce 2-second webm/opus chunks, which are streamed over WebSocket to the backend. Each chunk is transcribed independently, giving near-real-time output.

### Summarization
On demand (not automatic) to avoid hallucination. Long transcripts are split into ~900-word chunks, each summarized separately, then joined. Key points are extracted from the final summary.

---

## What to do next (development roadmap)

### Phase 1 — Accuracy (do this first)
- [ ] Upgrade Whisper model from `base` → `small` or `medium` for better Tagalog/Cebuano accuracy
- [ ] Test with real lecture audio; tune `CONF_THRESHOLD` in `jargon.py`
- [ ] Add a domain-specific vocabulary list (academic terms) to reduce jargon false-positives
- [ ] Experiment with `csebuetnlp/mT5_multilingual_XLSum` for multilingual summarization

### Phase 2 — Features
- [ ] Speaker diarization (pyannote-audio): label who is speaking
- [ ] Timestamped transcript segments (already in session data, expose in UI)
- [ ] Per-language confidence display in Streamlit
- [ ] Jargon definition lookup (Wikipedia API)
- [ ] Edit mode: user can correct flagged words inline

### Phase 3 — Robustness
- [ ] Replace in-memory `session.py` with SQLite (`aiosqlite`) for persistence across restarts
- [ ] Add authentication to the FastAPI server
- [ ] Handle reconnection in the WebSocket (exponential backoff)
- [ ] Unit tests for `transcriber.py`, `jargon.py`, `summarizer.py`

### Phase 4 — Thesis evaluation
- [ ] WER (Word Error Rate) measurement against ground-truth transcripts
- [ ] ROUGE score for summarizer evaluation
- [ ] User study: lecturers rate transcript accuracy for each language
- [ ] Latency benchmarks: audio-in → transcript-out time per model size

---

## Environment variables (optional)

Create a `.env` file in `backend/`:

```
SUMMARIZER_MODEL=facebook/bart-large-cnn
# or: csebuetnlp/mT5_multilingual_XLSum
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Extension can't connect | Make sure backend is running on port 8000 |
| No transcript appears | Check Chrome DevTools → Service Worker logs |
| "tabCapture failed" | Extension must be active on a Meet tab, not a background tab |
| Whisper very slow | Use a smaller model (`tiny`/`base`) or enable GPU |
| Cebuano detected as Tagalog | This is expected; set `CEBUANO_REMAP=True` in `transcriber.py` |

