"""
backend/jargon.py
Detects words that Whisper is uncertain about or that fall
outside a basic vocabulary — flagged as potential jargon,
technical terms, or misrecognized words.

Strategy (two-pass):
  1. Low probability: any word with Whisper probability < CONF_THRESHOLD
  2. OOV heuristic:  words not in a small common-word list that also
     look unusual (all-caps, mixed case, long, or hyphenated)

Jargon is SURFACED but NEVER removed from the transcript — we keep
the original text intact and let the user decide.
"""

import re
from pathlib import Path

CONF_THRESHOLD = 0.70        # below this → low confidence
MIN_WORD_LEN   = 4           # short words (articles etc.) are ignored
OOV_WORD_RE    = re.compile(
    r"^[A-Z]{2,}$"            # all-caps abbreviation  e.g. PCR, ATP
    r"|^[A-Z][a-z]+[A-Z]"     # camelCase              e.g. mRNA
    r"|^[a-z]+-[a-z]+"        # hyphenated compound    e.g. co-factor
    r"|^\d+[a-zA-Z]+"         # numeric prefix         e.g. 3D, 5G
    r"|^[a-zA-Z]{12,}$",      # very long word         e.g. phosphorylation
    re.UNICODE,
)

# Load a small list of common English / Filipino words to reduce false positives
_COMMON_WORDS: set[str] = set()


def _load_common_words():
    global _COMMON_WORDS
    # Fallback minimal list – extend with a real wordlist file if needed
    _COMMON_WORDS = {
        # English function words
        "the", "and", "that", "this", "with", "from", "have", "will", "your",
        "what", "when", "where", "which", "their", "there", "been", "were",
        "they", "some", "than", "then", "into", "more", "also", "about",
        # Common Filipino/Tagalog particles
        "ang", "mga", "ako", "ikaw", "siya", "kami", "tayo", "sila",
        "ito", "iyan", "iyon", "dito", "doon", "diyan", "hindi", "ngayon",
        "kaya", "kung", "para", "nang", "lang", "lamang", "dahil",
        # Common Cebuano
        "ang", "mga", "ako", "ikaw", "siya", "kami", "kita", "sila",
        "dili", "wala", "karon", "diri", "didto",
    }


_load_common_words()


class JargonDetector:
    def detect(self, full_text: str, segments: list) -> list[dict]:
        """
        Analyse Whisper segments and return a list of flagged words.

        Each flagged entry:
          { word, reason, probability, start, end }
        """
        flagged: list[dict] = []

        for seg in segments:
            for w in seg.get("words", []):
                word = w["word"].strip().rstrip(".,!?;:")
                prob = w.get("probability", 1.0)

                reason = self._flag_reason(word, prob)
                if reason:
                    flagged.append({
                        "word":        word,
                        "reason":      reason,
                        "probability": prob,
                        "start":       w["start"],
                        "end":         w["end"],
                    })

        # Deduplicate by word (keep first occurrence)
        seen = set()
        unique = []
        for f in flagged:
            key = f["word"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(f)

        return unique

    # ── internal ─────────────────────────────────────────

    def _flag_reason(self, word: str, prob: float) -> str | None:
        if len(word) < MIN_WORD_LEN:
            return None
        if word.lower() in _COMMON_WORDS:
            return None

        if prob < CONF_THRESHOLD:
            return "low_confidence"

        if OOV_WORD_RE.match(word):
            return "possible_jargon"

        return None
