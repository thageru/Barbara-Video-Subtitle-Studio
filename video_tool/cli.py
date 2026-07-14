from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .languages import LANGUAGES, language_codes
from .processor import ProcessingError, ProcessingRequest, SubtitleStyle, process_video, resolve_ffmpeg
from .transcriber import SubtitleGenerationRequest, generate_subtitles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="videoctl",
        description="Offline local video subtitle processing tool.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    process_parser = subparsers.add_parser("process", help="add subtitles to a local video")
    process_parser.add_argument("--video", required=True, type=Path, help="input video path")
    process_parser.add_argument("--subtitle", type=Path, help="input subtitle path (.srt/.ass/.ssa/.vtt); not used by strip-soft")
    process_parser.add_argument(
        "--mode",
        required=True,
        choices=["burn", "external", "strip-soft"],
        help="burn: hard-code subtitles; external: copy a sidecar SRT; strip-soft: remove embedded subtitle streams",
    )
    process_parser.add_argument(
        "--language",
        default="zh-Hans",
        help=f"subtitle language tag; built-ins: {', '.join(language_codes())}",
    )
    process_parser.add_argument("--output-dir", type=Path, help="directory for generated file")
    process_parser.add_argument("--output", type=Path, help="exact output file path")
    process_parser.add_argument("--ffmpeg", help="explicit ffmpeg binary path")
    process_parser.add_argument("--font-size", type=int, default=22, help="burned subtitle font size; default: 22")
    process_parser.add_argument("--subtitle-y", type=float, default=2.0, help="burned subtitle bottom margin as percent of video height; default: 2")

    subtitle_parser = subparsers.add_parser("subtitles", help="generate subtitle files from a local video")
    subtitle_parser.add_argument("--video", required=True, type=Path, help="input video path")
    subtitle_parser.add_argument(
        "--languages",
        default="zh-Hans",
        help="comma-separated subtitle languages, e.g. zh-Hans or zh-Hans,en",
    )
    subtitle_parser.add_argument("--subtitle-dir", type=Path, help="directory for generated subtitle files; defaults to video folder")
    subtitle_parser.add_argument("--subtitle-name", help="base subtitle file name; defaults to video file name")
    subtitle_parser.add_argument("--model", default="small", help="WhisperKit model name; default: small")
    subtitle_parser.add_argument("--source-language", default="zh", help="spoken source language for translation; default: zh")
    subtitle_parser.add_argument("--burn", action="store_true", help="also burn the generated subtitle into MP4; only valid with one language")
    subtitle_parser.add_argument("--no-overwrite", action="store_true", help="refuse to replace existing subtitle files")
    subtitle_parser.add_argument("--font-size", type=int, default=22, help="burned subtitle font size when --burn is used")
    subtitle_parser.add_argument("--subtitle-y", type=float, default=2.0, help="burned subtitle bottom margin percent when --burn is used")

    subparsers.add_parser("languages", help="list supported language presets")
    subparsers.add_parser("doctor", help="check local runtime dependencies")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "languages":
            for language in LANGUAGES:
                print(f"{language.code}\t{language.ffmpeg_tag}\t{language.label}")
            return 0

        if args.command == "doctor":
            ffmpeg = resolve_ffmpeg(None)
            print(f"ffmpeg: {ffmpeg}")
            print("python: ok")
            return 0


        if args.command == "subtitles":
            results = generate_subtitles(
                SubtitleGenerationRequest(
                    video_path=args.video,
                    language_codes=[part.strip() for part in args.languages.split(",")],
                    subtitle_dir=args.subtitle_dir,
                    subtitle_basename=args.subtitle_name,
                    model=args.model,
                    source_language=args.source_language,
                    overwrite=not args.no_overwrite,
                    burn=args.burn,
                    style=SubtitleStyle(font_size=args.font_size, y_percent=args.subtitle_y),
                )
            )
            for result in results:
                print(f"language: {result.language.code} ({result.language.label})")
                print(f"subtitle: {result.subtitle_path}")
                print(f"entries: {result.entries}")
                if result.hardsub_path:
                    print(f"hardsub: {result.hardsub_path}")
            return 0

        if args.command == "process":
            if args.mode != "strip-soft" and args.subtitle is None:
                raise ProcessingError("--subtitle is required for burn and external modes")
            result = process_video(
                ProcessingRequest(
                    video_path=args.video,
                    subtitle_path=args.subtitle,
                    mode=args.mode,
                    language_code=args.language,
                    output_dir=args.output_dir,
                    output_path=args.output,
                    ffmpeg_bin=args.ffmpeg,
                    style=SubtitleStyle(font_size=args.font_size, y_percent=args.subtitle_y),
                )
            )
            print(f"mode: {result.mode}")
            print(f"language: {result.language.code} ({result.language.label})")
            print(f"output: {result.output_path}")
            return 0

    except ProcessingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
