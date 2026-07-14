from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SRT_TIME = re.compile(r"\d\d:\d\d:\d\d,\d\d\d\s+-->\s+\d\d:\d\d:\d\d,\d\d\d(?:\s+.*)?")
NON_SPEECH_LABELS = {
    "music",
    "music playing",
    "background music",
    "upbeat music",
    "gentle music",
    "instrumental music",
    "sound effect",
    "sound effects",
    "sfx",
    "blank audio",
    "blank_audio",
    "silence",
    "applause",
    "laughter",
}


@dataclass(frozen=True)
class SrtEntry:
    index: int
    timecode: str
    text: str


def parse_srt(path: Path) -> list[SrtEntry]:
    content = Path(path).expanduser().read_text(encoding="utf-8-sig").replace("\r", "")
    return parse_srt_text(content)


def parse_srt_text(content: str) -> list[SrtEntry]:
    content = str(content or "").lstrip("\ufeff").replace("\r", "")
    blocks = [block for block in content.split("\n\n") if block.strip()]
    entries: list[SrtEntry] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue
        timecode = lines[1].strip()
        if not SRT_TIME.fullmatch(timecode):
            continue
        text_lines = [line.strip() for line in lines[2:] if line.strip()]
        if not text_lines:
            continue
        entries.append(SrtEntry(index=index, timecode=timecode, text="\n".join(text_lines)))
    return entries


def write_srt(entries: list[SrtEntry], texts: list[str], output: Path) -> None:
    if len(entries) != len(texts):
        raise ValueError(f"SRT count mismatch: entries={len(entries)} texts={len(texts)}")
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for idx, (entry, text) in enumerate(zip(entries, texts), start=1):
        cleaned = _clean_text(text)
        if not cleaned:
            cleaned = " "
        blocks.append("\n".join([str(idx), entry.timecode, cleaned]))
    output.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_manual_translation(
    entries: list[SrtEntry],
    translations: list[str],
    output: Path,
    bilingual: bool = False,
) -> None:
    texts: list[str] = []
    for entry, translation in zip(entries, translations):
        cleaned = _clean_text(translation)
        if bilingual:
            source = _clean_text(entry.text)
            texts.append(f"{source}\n{cleaned}" if cleaned else source)
        else:
            texts.append(cleaned)
    write_srt(entries, texts, output)


def default_translated_path(source: Path, target_language: str = "zh-Hans") -> Path:
    source = Path(source).expanduser().resolve()
    stem = source.stem
    if stem.endswith(".en"):
        stem = stem[:-3]
    return source.with_name(f"{stem}.{target_language}.srt")


def is_non_speech_text(text: str) -> bool:
    normalized = str(text or "").casefold().replace("♪", "").replace("♫", "").strip()
    normalized = normalized.strip("[](){}<> ")
    return not normalized or normalized in NON_SPEECH_LABELS


def _clean_text(value: str) -> str:
    lines = [line.strip() for line in str(value or "").replace("\r", "").splitlines()]
    return "\n".join(line for line in lines if line)
