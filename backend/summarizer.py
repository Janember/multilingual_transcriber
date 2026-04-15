"""
backend/summarizer.py
Loads BART directly (no pipeline) — compatible with any transformers version.
"""

from transformers import BartForConditionalGeneration, BartTokenizer
import os

SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "facebook/bart-large-cnn")
MAX_SUMMARY_LEN  = 256
MIN_SUMMARY_LEN  = 60
CHUNK_SIZE       = 900   # words per chunk


class Summarizer:
    def __init__(self):
        print(f"[Summarizer] Loading {SUMMARIZER_MODEL}…")
        self._tokenizer = BartTokenizer.from_pretrained(SUMMARIZER_MODEL)
        self._model     = BartForConditionalGeneration.from_pretrained(SUMMARIZER_MODEL)
        self._model.eval()
        print("[Summarizer] Ready.")

    def summarize(self, text: str) -> dict:
        words  = text.split()
        chunks = [words[i : i + CHUNK_SIZE] for i in range(0, len(words), CHUNK_SIZE)]

        summaries = []
        for chunk in chunks:
            chunk_text = " ".join(chunk)
            inputs = self._tokenizer(
                chunk_text,
                return_tensors="pt",
                max_length=1024,
                truncation=True,
            )
            ids = self._model.generate(
                inputs["input_ids"],
                max_new_tokens=MAX_SUMMARY_LEN,
                min_new_tokens=MIN_SUMMARY_LEN,
                num_beams=4,
                early_stopping=True,
            )
            summaries.append(
                self._tokenizer.decode(ids[0], skip_special_tokens=True)
            )

        final      = " ".join(summaries)
        key_points = [s.strip() for s in final.split(".") if len(s.strip()) > 20][:7]

        return {
            "summary":     final,
            "key_points":  key_points,
            "chunks_used": len(chunks),
        }
