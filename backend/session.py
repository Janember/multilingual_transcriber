"""
backend/session.py  (code-switching aware)
Stores per-segment language alongside the transcript entry.
"""

from datetime import datetime
import re

LANG_LABELS = {
    "en":  "🇺🇸 EN",
    "tl":  "🇵🇭 TL",
    "ceb": "🇵🇭 CEB",
    "??":  "❓",
}

LANG_TO_CODE = {
    "english":  "en",
    "tagalog":  "tl",
    "filipino": "tl",
    "cebuano":  "ceb",
}

STRIP_MARKERS = re.compile(r"\[(?:EN|TL|CEB|\?\?)\]\s*")


class TranscriptSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self._entries: list[dict] = []
        self._jargon:  list[dict] = []
        self._notes:   dict       = {}
        self._started: str        = datetime.utcnow().isoformat()

    def append(
        self,
        text: str,
        language: str,
        jargon: list[dict],
        segments: list | None = None,
        code_switched: bool = False,
    ) -> dict:
        language_code = LANG_TO_CODE.get(
            language.lower(),
            language[:2].lower() if language else "??"
        )
        entry = {
            "id":            len(self._entries),
            "text":          text,
            "language":      language,
            "language_code": language_code,   # ← bug fix: now always stored
            "segments":      segments or [],
            "code_switched": code_switched,
            "timestamp":     datetime.utcnow().isoformat(),
            "jargon":        jargon,
        }
        self._entries.append(entry)

        existing = {j["word"].lower() for j in self._jargon}
        for j in jargon:
            if j["word"].lower() not in existing:
                self._jargon.append(j)
                existing.add(j["word"].lower())

        return entry

    def set_notes(self, notes: dict):
        self._notes = notes

    def full_text(self) -> str:
        raw = " ".join(e["text"] for e in self._entries)
        return STRIP_MARKERS.sub("", raw)

    def all_jargon(self) -> list[dict]:
        return self._jargon

    def language_stats(self) -> dict:
        from collections import Counter
        counts = Counter()
        for e in self._entries:
            for seg in e.get("segments", []):
                code = seg.get("language_code", e.get("language_code", "??"))
                counts[code] += 1
        return dict(counts)

    def code_switch_count(self) -> int:
        return sum(1 for e in self._entries if e.get("code_switched"))

    def to_dict(self) -> dict:
        return {
            "started":           self._started,
            "entries":           self._entries,
            "jargon":            self._jargon,
            "notes":             self._notes,
            "language_stats":    self.language_stats(),
            "code_switch_count": self.code_switch_count(),
        }

    def to_txt(self) -> str:
        lines = [f"# Session started {self._started}", ""]
        for e in self._entries:
            ts    = e["timestamp"][11:19]
            label = LANG_LABELS.get(e.get("language_code", "??"), "❓")
            cs    = " ⇄" if e.get("code_switched") else ""
            clean = STRIP_MARKERS.sub("", e["text"])
            lines.append(f"[{ts}] {label}{cs}  {clean}")
            if e.get("code_switched") and e.get("segments"):
                for seg in e["segments"]:
                    seg_label = LANG_LABELS.get(seg.get("language_code", "??"), "❓")
                    lines.append(f"    {seg_label}  {seg['text']}")
        if self._notes:
            lines += ["", "## Summary", self._notes.get("summary", "")]
            lines += ["", "## Key points"]
            for kp in self._notes.get("key_points", []):
                lines.append(f"- {kp}")
        if self._jargon:
            lines += ["", "## Flagged terms"]
            for j in self._jargon:
                lines.append(f"- {j['word']} ({j['reason']})")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        return self.to_txt()