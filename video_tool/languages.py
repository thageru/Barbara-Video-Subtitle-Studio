from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleLanguage:
    code: str
    label: str
    ffmpeg_tag: str


LANGUAGES: tuple[SubtitleLanguage, ...] = (
    SubtitleLanguage("zh-Hans", "Chinese Simplified", "chi"),
    SubtitleLanguage("zh-Hant", "Chinese Traditional", "chi"),
    SubtitleLanguage("en", "English", "eng"),
    SubtitleLanguage("ja", "Japanese", "jpn"),
    SubtitleLanguage("ko", "Korean", "kor"),
    SubtitleLanguage("fr", "French", "fra"),
    SubtitleLanguage("de", "German", "deu"),
    SubtitleLanguage("es", "Spanish", "spa"),
)


def language_codes() -> list[str]:
    return [language.code for language in LANGUAGES]


def find_language(code: str) -> SubtitleLanguage:
    normalized = code.strip()
    for language in LANGUAGES:
        if language.code == normalized:
            return language
    if not normalized:
        raise ValueError("subtitle language is required")
    # Allow private/custom tags while keeping a deterministic ffmpeg metadata tag.
    return SubtitleLanguage(normalized, f"Custom ({normalized})", normalized[:3].lower())
