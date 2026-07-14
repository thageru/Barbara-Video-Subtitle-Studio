from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .languages import SubtitleLanguage, find_language
from .chinese import to_simplified_chinese
from .processor import ProcessingError, ProcessingRequest, SubtitleStyle, VIDEO_EXTENSIONS, process_video
from .paths import output_directory
from .srt import is_non_speech_text


@dataclass(frozen=True)
class SubtitleGenerationRequest:
    video_path: Path
    language_codes: list[str]
    subtitle_dir: Path | None = None
    subtitle_basename: str | None = None
    model: str = "small"
    source_language: str = "zh"
    overwrite: bool = True
    burn: bool = False
    ffmpeg_bin: str | None = None
    style: SubtitleStyle = SubtitleStyle()


@dataclass(frozen=True)
class SubtitleGenerationResult:
    language: SubtitleLanguage
    subtitle_path: Path
    hardsub_path: Path | None
    entries: int
    command: list[str]


def generate_subtitles(request: SubtitleGenerationRequest) -> list[SubtitleGenerationResult]:
    video = _existing_video(request.video_path)
    languages = _resolve_languages(request.language_codes)
    if request.burn and len(languages) != 1:
        raise ProcessingError("burn mode supports exactly one subtitle language at a time")

    subtitle_dir = output_directory(video, request.subtitle_dir)
    basename = _safe_basename(request.subtitle_basename or video.stem)

    whisperkit = resolve_whisperkit()
    results: list[SubtitleGenerationResult] = []
    for language in languages:
        subtitle_path = subtitle_dir / f"{basename}.{language.code}.srt"
        if subtitle_path.exists() and not request.overwrite:
            raise ProcessingError(f"refusing to overwrite existing subtitle: {subtitle_path}")

        entries, command = _transcribe_with_whisperkit(
            whisperkit=whisperkit,
            video=video,
            model=request.model,
            output_language=language.code,
            source_language=request.source_language,
            destination=subtitle_path,
            simplify=language.code == "zh-Hans",
        )
        if entries == 0:
            raise ProcessingError(f"no subtitle entries generated for {language.code}")

        hardsub_path: Path | None = None
        if request.burn:
            hardsub_path = subtitle_dir / f"{basename}.{language.code}.hardsub.mp4"
            process_video(
                ProcessingRequest(
                    video_path=video,
                    subtitle_path=subtitle_path,
                    mode="burn",
                    language_code=language.code,
                    output_path=hardsub_path,
                    ffmpeg_bin=request.ffmpeg_bin,
                    style=request.style,
                )
            )

        results.append(
            SubtitleGenerationResult(
                language=language,
                subtitle_path=subtitle_path,
                hardsub_path=hardsub_path,
                entries=entries,
                command=command,
            )
        )
    return results


def default_subtitle_dir(video_path: Path) -> Path:
    return output_directory(video_path)


def default_subtitle_basename(video_path: Path) -> str:
    return Path(video_path).expanduser().resolve().stem


def resolve_whisperkit(explicit: str | None = None) -> str:
    candidates = [explicit, shutil.which("whisperkit-cli"), "/opt/homebrew/bin/whisperkit-cli"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise ProcessingError("whisperkit-cli not found; install it or add it to PATH")


def normalize_srt(source: Path, destination: Path, simplify: bool = False) -> int:
    content = source.read_text(encoding="utf-8")
    blocks = [block for block in content.replace("\r", "").split("\n\n") if block.strip()]

    cleaned_blocks: list[str] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if len(lines) < 3:
            continue
        timecode = lines[1].strip()
        text_lines = [line.strip() for line in lines[2:] if line.strip()]
        if not text_lines:
            continue
        if _is_non_speech_cue(text_lines):
            continue
        if simplify:
            text_lines = [to_simplified_chinese(line) for line in text_lines]
        cleaned_blocks.append("\n".join([str(len(cleaned_blocks) + 1), timecode, *text_lines]))

    if not cleaned_blocks:
        if destination.exists():
            destination.unlink()
        return 0

    destination.write_text("\n\n".join(cleaned_blocks) + "\n", encoding="utf-8")
    return len(cleaned_blocks)


def _is_non_speech_cue(lines: list[str]) -> bool:
    """Drop music and sound-effect labels, but keep spoken text containing them."""
    return is_non_speech_text(" ".join(lines))

def _transcribe_with_whisperkit(
    whisperkit: str,
    video: Path,
    model: str,
    output_language: str,
    source_language: str,
    destination: Path,
    simplify: bool,
) -> tuple[int, list[str]]:
    with tempfile.TemporaryDirectory(prefix="video-subtitles-") as temp_name:
        report_dir = Path(temp_name) / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        task = "transcribe"
        language = "en" if output_language == "en" else _whisper_language(output_language)
        command = [
            whisperkit,
            "transcribe",
            "--audio-path",
            str(video),
            "--model",
            model,
            "--task",
            task,
            "--language",
            language,
            "--skip-special-tokens",
            "--report",
            "--report-path",
            str(report_dir),
        ]
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise ProcessingError(process.stdout.strip() or "whisperkit-cli failed")

        raw_srt = report_dir / f"{video.stem}.srt"
        if not raw_srt.is_file():
            candidates = sorted(report_dir.glob("*.srt"))
            if not candidates:
                raise ProcessingError(f"WhisperKit did not generate an SRT in {report_dir}")
            raw_srt = candidates[0]

        entries = normalize_srt(raw_srt, destination, simplify=simplify)
        return entries, command



def _resolve_languages(language_codes: list[str]) -> list[SubtitleLanguage]:
    codes = [code.strip() for code in language_codes if code.strip()]
    if not codes:
        raise ProcessingError("at least one subtitle language is required")
    return [find_language(code) for code in codes]


def _existing_video(path: Path) -> Path:
    video = Path(path).expanduser().resolve()
    if not video.is_file():
        raise ProcessingError(f"video file does not exist: {video}")
    if video.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ProcessingError(f"unsupported video extension: {video.suffix}")
    return video


def _safe_basename(value: str) -> str:
    name = Path(value.strip()).name
    if not name:
        raise ProcessingError("subtitle file name is required")
    if name.endswith(".srt"):
        name = name[:-4]
    return name


def _whisper_language(code: str) -> str:
    if code in {"zh-Hans", "zh-Hant", "zh"}:
        return "zh"
    return code.split("-", 1)[0]


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
