"""
backend/transcriber.py
Single-pass transcription with language filtering and initial_prompt.
No retry loops — one Whisper call per chunk for speed.
"""

import whisper
import torch
from collections import Counter

# ── Config ────────────────────────────────────────────────

NO_SPEECH_THRESHOLD = 0.65   # skip segment if Whisper doubts speech
AVG_LOGPROB_FLOOR   = -1.2   # skip segment if confidence too low

ACCEPTED_LANGUAGES = {
    "english", "tagalog", "filipino", "cebuano",  
    "en", "tl", "fil", "ceb",                     
}

# Biases Whisper toward Philippine English and Filipino speech patterns.
# This single line meaningfully improves accuracy for code-switched speech.
INITIAL_PROMPT = (
    "This is a university lecture. The speaker uses English, Tagalog, and Cebuano Filipino. "
    "Common Filipino words: ang, mga, na, sa, ng, ay, at, ito, siya, niya, ko, mo, naman, "
    "kaya, pero, dahil, talaga, lang, din, rin, dito, kung, bakit, paano, tayo, kami."
)

LANG_CODE_MAP = {
    "english":  "en",
    "tagalog":  "tl",
    "filipino": "tl",
    "cebuano":  "ceb",
}


class WhisperTranscriber:
    def __init__(self, model_size: str = "medium"):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Whisper] Loading model '{model_size}' on {device}…")
        self.model  = whisper.load_model(model_size, device=device)
        self.device = device
        print("[Whisper] Model ready.")

    def transcribe(self, audio_path: str, language: str | None = None) -> dict:
        """
        Single-pass transcription.
        - Uses initial_prompt to bias toward Philippine English/Filipino
        - Filters segments by no_speech_prob and avg_logprob
        - Discards chunks where Whisper detected a non-target language
          without running a second pass (much faster)
        """
        result = self.model.transcribe(
            audio_path,
            task="transcribe",
            language=language,          # None = auto-detect
            word_timestamps=True,
            verbose=False,
            initial_prompt=INITIAL_PROMPT,
            temperature=0.0,            # greedy decoding = faster + more consistent
            condition_on_previous_text=True,
        )

        detected_lang = result.get("language", "unknown").lower()
        print(f"[Whisper] Detected: {detected_lang}")

        # Discard chunk if Whisper detected an out-of-scope language
        # (no retry — just drop it, the next chunk will be better)
        if detected_lang not in ACCEPTED_LANGUAGES:
            print(f"[Whisper] Dropping chunk – detected '{detected_lang}' (not EN/TL/CEB)")
            return self._empty_result()

        # Remap filipino → tagalog code
        lang_code = LANG_CODE_MAP.get(detected_lang, detected_lang[:2])

        # Filter low-quality segments
        segments = []
        for seg in result.get("segments", []):
            no_speech = seg.get("no_speech_prob", 0.0)
            logprob   = seg.get("avg_logprob", -1.0)
            text      = seg.get("text", "").strip()

            if not text:
                continue
            if no_speech > NO_SPEECH_THRESHOLD:
                print(f"[Whisper] Skipped (no_speech={no_speech:.2f}): '{text}'")
                continue
            if logprob < AVG_LOGPROB_FLOOR:
                print(f"[Whisper] Skipped (logprob={logprob:.2f}): '{text}'")
                continue

            segments.append({
                "start":          round(seg["start"], 2),
                "end":            round(seg["end"], 2),
                "text":           text,
                "language":       detected_lang,
                "language_code":  lang_code,
                "avg_logprob":    round(logprob, 4),
                "no_speech_prob": round(no_speech, 4),
                "words":          self._clean_words(seg.get("words", [])),
            })

        if not segments:
            return self._empty_result()

        full_text = " ".join(s["text"] for s in segments)
        dominant  = Counter(s["language"] for s in segments).most_common(1)[0][0]

        return {
            "text":          full_text,
            "language":      dominant,
            "language_code": LANG_CODE_MAP.get(dominant, dominant[:2]),
            "segments":      segments,
            "code_switched": len({s["language"] for s in segments}) > 1,
        }

    @staticmethod
    def _clean_words(words: list) -> list:
        return [
            {
                "word":        w["word"].strip(),
                "start":       round(w["start"], 2),
                "end":         round(w["end"], 2),
                "probability": round(w.get("probability", 1.0), 4),
            }
            for w in words
        ]

    @staticmethod
    def _empty_result() -> dict:
        return {
            "text":         "",
            "language":     "unknown",
            "language_code": "??",
            "segments":     [],
            "code_switched": False,
        }