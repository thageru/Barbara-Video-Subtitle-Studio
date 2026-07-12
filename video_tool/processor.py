from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .languages import SubtitleLanguage, find_language
from .paths import output_directory

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}


class ProcessingError(RuntimeError):
    """Raised when a video processing job cannot be completed."""


@dataclass(frozen=True)
class SubtitleStyle:
    font_size: int = 22
    y_percent: float = 2.0


@dataclass(frozen=True)
class ProcessingRequest:
    video_path: Path
    subtitle_path: Path
    mode: str
    language_code: str
    output_dir: Path | None = None
    output_path: Path | None = None
    ffmpeg_bin: str | None = None
    style: SubtitleStyle = SubtitleStyle()


@dataclass(frozen=True)
class ProcessingResult:
    output_path: Path
    mode: str
    command: list[str] | None
    language: SubtitleLanguage


def process_video(request: ProcessingRequest) -> ProcessingResult:
    video_path = _existing_file(request.video_path, "video")
    subtitle_path = _existing_file(request.subtitle_path, "subtitle")
    mode = request.mode.strip().lower()
    language = find_language(request.language_code)

    if video_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ProcessingError(f"unsupported video extension: {video_path.suffix}")
    if subtitle_path.suffix.lower() not in SUBTITLE_EXTENSIONS:
        raise ProcessingError(f"unsupported subtitle extension: {subtitle_path.suffix}")

    requested_root = request.output_dir or (request.output_path.parent if request.output_path else None)
    output_dir = output_directory(video_path, requested_root)
    output_path = output_dir / request.output_path.name if request.output_path else None

    if mode in {"external", "sidecar", "外挂字幕"}:
        return _create_external_subtitle(video_path, subtitle_path, language, output_dir, output_path)
    if mode in {"burn", "hard", "hardsub", "烧录"}:
        return _burn_subtitle(video_path, subtitle_path, language, output_dir, output_path, request.ffmpeg_bin, request.style)

    raise ProcessingError("mode must be 'burn' or 'external'")


def render_subtitle_preview(
    video_path: Path,
    subtitle_path: Path,
    timestamp: float,
    style: SubtitleStyle,
    output_dir: Path | None = None,
    ffmpeg_bin: str | None = None,
) -> tuple[Path, list[str]]:
    video = _existing_file(video_path, "video")
    subtitle = _existing_file(subtitle_path, "subtitle")
    ffmpeg = resolve_ffmpeg(ffmpeg_bin)
    _require_subtitles_filter(ffmpeg)
    directory = output_dir or Path(os.environ.get("TMPDIR", "/tmp"))
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"videoprocess-preview-{uuid.uuid4().hex}.png"
    subtitle_filter = build_subtitle_filter(subtitle, video, style, ffmpeg_bin=ffmpeg_bin)
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(video),
        "-vframes",
        "1",
        "-vf",
        subtitle_filter,
        str(target),
    ]
    _run(command)
    return target, command


def build_subtitle_filter(
    subtitle_path: Path,
    video_path: Path,
    style: SubtitleStyle,
    ffmpeg_bin: str | None = None,
) -> str:
    width, height = probe_video_size(video_path, ffmpeg_bin=ffmpeg_bin)
    del width
    font_size = _clamp_int(style.font_size, 8, 128)
    y_percent = _clamp_float(style.y_percent, 0.0, 100.0)
    margin_v = max(0, int(height * y_percent / 100.0))
    force_style = f"FontSize={font_size},MarginV={margin_v},Alignment=2"
    value = _escape_filter_value(str(Path(subtitle_path).expanduser().resolve()))
    return f"subtitles=filename='{value}':force_style='{force_style}'"


def probe_video_size(video_path: Path, ffmpeg_bin: str | None = None) -> tuple[int, int]:
    video = _existing_file(video_path, "video")
    ffprobe = resolve_ffprobe(ffmpeg_bin)
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(video),
    ]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if process.returncode != 0:
        raise ProcessingError(process.stdout.strip() or "ffprobe failed")
    raw = process.stdout.strip().splitlines()[0] if process.stdout.strip() else ""
    try:
        width_text, height_text = raw.split("x", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, IndexError) as exc:
        raise ProcessingError(f"could not read video size from ffprobe output: {raw}") from exc
    return width, height


def _create_external_subtitle(
    video_path: Path,
    subtitle_path: Path,
    language: SubtitleLanguage,
    output_dir: Path,
    output_path: Path | None,
) -> ProcessingResult:
    target = output_path or output_dir / f"{video_path.stem}.{language.code}{subtitle_path.suffix.lower()}"
    if target.resolve() != subtitle_path.resolve():
        shutil.copy2(subtitle_path, target)
    return ProcessingResult(output_path=target, mode="external", command=None, language=language)


def _burn_subtitle(
    video_path: Path,
    subtitle_path: Path,
    language: SubtitleLanguage,
    output_dir: Path,
    output_path: Path | None,
    ffmpeg_bin: str | None,
    style: SubtitleStyle,
) -> ProcessingResult:
    ffmpeg = resolve_ffmpeg(ffmpeg_bin)
    _require_subtitles_filter(ffmpeg)

    target = output_path or output_dir / f"{video_path.stem}.{language.code}.hardsub.mp4"
    if target.resolve() == video_path.resolve():
        raise ProcessingError("output path must be different from input video path")

    subtitle_filter = build_subtitle_filter(subtitle_path, video_path, style, ffmpeg_bin=ffmpeg_bin)
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        subtitle_filter,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-sn",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(target),
    ]
    _run(command)
    return ProcessingResult(output_path=target, mode="burn", command=command, language=language)


def resolve_ffmpeg(explicit: str | None = None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_value = os.environ.get("FFMPEG_BIN")
    if env_value:
        candidates.append(env_value)
    candidates.extend(
        [            "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "ffmpeg",
        ]
    )
    for candidate in candidates:
        resolved = shutil.which(candidate) if os.path.basename(candidate) == candidate else candidate
        if resolved and Path(resolved).exists():
            return resolved
    raise ProcessingError("ffmpeg not found; install ffmpeg or set FFMPEG_BIN=/path/to/ffmpeg")


def resolve_ffprobe(ffmpeg_bin: str | None = None) -> str:
    candidates: list[str] = []
    if ffmpeg_bin:
        ffmpeg_path = Path(ffmpeg_bin)
        if ffmpeg_path.name == "ffmpeg":
            candidates.append(str(ffmpeg_path.with_name("ffprobe")))
    env_value = os.environ.get("FFPROBE_BIN")
    if env_value:
        candidates.append(env_value)
    for ffmpeg_candidate in [resolve_ffmpeg(ffmpeg_bin)]:
        path = Path(ffmpeg_candidate)
        if path.name == "ffmpeg":
            candidates.append(str(path.with_name("ffprobe")))
    candidates.extend(["/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe", "ffprobe"])
    for candidate in candidates:
        resolved = shutil.which(candidate) if os.path.basename(candidate) == candidate else candidate
        if resolved and Path(resolved).exists():
            return resolved
    raise ProcessingError("ffprobe not found; install ffmpeg/ffprobe or set FFPROBE_BIN=/path/to/ffprobe")


def _require_subtitles_filter(ffmpeg: str) -> None:
    process = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise ProcessingError("failed to inspect ffmpeg filters")
    if " subtitles " not in process.stdout and " ass " not in process.stdout:
        raise ProcessingError(
            "ffmpeg lacks libass subtitles support; use ffmpeg-full or another build with the subtitles filter"
        )


def _run(command: Iterable[str]) -> None:
    process = subprocess.run(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise ProcessingError(process.stdout.strip() or "ffmpeg failed")


def _existing_file(path: Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise ProcessingError(f"{label} file does not exist: {resolved}")
    if not resolved.is_file():
        raise ProcessingError(f"{label} path is not a file: {resolved}")
    return resolved


def _escape_filter_value(value: str) -> str:
    # Escaping is for ffmpeg's filter parser, not for the shell. Commands are passed as argv.
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))
