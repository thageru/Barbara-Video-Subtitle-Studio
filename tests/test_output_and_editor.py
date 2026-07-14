from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_tool.chinese import to_simplified_chinese
from video_tool.paths import media_stem, organized_output_path, output_directory
from video_tool.processor import ProcessingRequest, SubtitleStyle, process_video, render_subtitle_preview
from video_tool.srt import parse_srt, write_manual_translation
from video_tool.translator import build_webchat_prompt, merge_webchat_translation
from video_tool.web import _srt_timestamp_seconds, render_editor, render_page


class OutputAndEditorTests(unittest.TestCase):
    def test_outputs_share_video_named_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name).resolve()
            video = root / "lesson.mp4"
            video.touch()

            self.assertEqual(output_directory(video), root / "lesson")
            self.assertEqual(output_directory(video, root / "lesson"), root / "lesson")
            self.assertEqual(
                organized_output_path(video, root / "lesson.zh-Hans.srt", "unused.srt"),
                root / "lesson" / "lesson.zh-Hans.srt",
            )

    def test_output_directory_does_not_nest_when_video_name_has_trailing_space(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name).resolve()
            organized = root / "S2 "
            organized.mkdir()
            subtitle = organized / "S2.en.srt"
            subtitle.touch()

            self.assertEqual(output_directory(subtitle, organized), organized)
            self.assertEqual(
                organized_output_path(subtitle, organized / "S2.zh-Hans.srt", "unused.srt"),
                organized / "S2.zh-Hans.srt",
            )

    def test_existing_subtitle_editor_prefills_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name).resolve()
            subtitle = root / "lesson" / "lesson.zh-Hans.srt"
            subtitle.parent.mkdir()
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nOriginal text\n", encoding="utf-8")

            page = render_editor(str(subtitle), str(subtitle), prefill=True)

            self.assertIn("在线编辑已有字幕", page)
            self.assertIn(">Original text</textarea>", page)
            self.assertIn('class="editor-table-wrap"', page)
            self.assertIn("setSavingState", page)
            self.assertEqual(media_stem(subtitle), "lesson")

    def test_manual_save_preserves_timing_and_simplifies_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name).resolve()
            source = root / "lesson.en.srt"
            output = root / "lesson" / "lesson.zh-Hans.srt"
            source.write_text("1\n00:00:00,000 --> 00:00:01,000\nWe learn\n", encoding="utf-8")
            entries = parse_srt(source)

            write_manual_translation(entries, [to_simplified_chinese("我們開始學習")], output)
            saved = parse_srt(output)

            self.assertEqual(saved[0].timecode, entries[0].timecode)
            self.assertEqual(saved[0].text, "我们开始学习")

    def test_home_page_contains_live_status_and_online_editor(self) -> None:
        page = render_page()
        self.assertIn("Barbara-Video-Subtitle-Studio", page)
        self.assertIn('id="job-notice"', page)
        self.assertIn('aria-live="polite"', page)
        self.assertIn('class="workflow-nav"', page)
        self.assertIn("prefers-reduced-motion", page)
        self.assertIn("watchedJobId", page)
        self.assertIn("在线编辑已有字幕", page)

    def test_webchat_prompt_contains_template_and_complete_srt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name) / "lesson.en.srt"
            source.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nWelcome back\n\n"
                "2\n00:00:02,000 --> 00:00:03,000\n[Music]\n\n"
                "3\n00:00:03,000 --> 00:00:04,000\nLet us begin\n\n"
                "4\n00:00:04,000 --> 00:00:05,000\n[BLANK_AUDIO]\n",
                encoding="utf-8",
            )

            prompt, entries, batches = build_webchat_prompt(source)

            self.assertEqual(entries, 2)
            self.assertEqual(batches, 1)
            self.assertIn("只返回完整 SRT 正文", prompt)
            self.assertIn("1\n00:00:01,000 --> 00:00:02,000\nWelcome back", prompt)
            self.assertIn("2\n00:00:03,000 --> 00:00:04,000\nLet us begin", prompt)
            self.assertNotIn("[Music]", prompt)
            self.assertNotIn("[BLANK_AUDIO]", prompt)

    def test_pasted_translated_srt_preserves_timing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "lesson.en.srt"
            output = root / "lesson.zh-Hans.srt"
            source.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nWelcome back\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\nLet us begin\n",
                encoding="utf-8",
            )
            response = (
                "```srt\n"
                "1\n00:00:01,000 --> 00:00:02,000\n欢迎回来\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\n我们开始吧\n"
                "```"
            )

            result = merge_webchat_translation(source, response, output)
            translated = parse_srt(output)

            self.assertEqual(result.entries, 2)
            self.assertEqual(translated[0].timecode, "00:00:01,000 --> 00:00:02,000")
            self.assertEqual(translated[1].text, "我们开始吧")

    def test_pasted_translated_srt_rejects_changed_timecode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "lesson.en.srt"
            output = root / "lesson.zh-Hans.srt"
            source.write_text("1\n00:00:01,000 --> 00:00:02,000\nWelcome\n", encoding="utf-8")
            changed = "1\n00:00:01,500 --> 00:00:02,500\n欢迎\n"

            with self.assertRaisesRegex(Exception, "changed the timecode"):
                merge_webchat_translation(source, changed, output)

    def test_preview_applies_seek_after_input_for_correct_subtitle_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            video = root / "lesson.mp4"
            subtitle = root / "lesson.srt"
            video.touch()
            subtitle.write_text("1\n00:00:10,000 --> 00:00:11,000\nPreview\n", encoding="utf-8")

            with (
                patch("video_tool.processor.resolve_ffmpeg", return_value="/usr/bin/ffmpeg"),
                patch("video_tool.processor._require_subtitles_filter"),
                patch("video_tool.processor.build_subtitle_filter", return_value="subtitles=test.srt"),
                patch("video_tool.processor._run") as run_mock,
            ):
                render_subtitle_preview(video, subtitle, 10.0, SubtitleStyle(), output_dir=root)

            command = run_mock.call_args.args[0]
            self.assertLess(command.index("-i"), command.index("-ss"))

    def test_strip_soft_subtitles_copies_streams_and_excludes_subtitles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            video = root / "lesson.mp4"
            video.touch()

            with (
                patch("video_tool.processor.resolve_ffmpeg", return_value="/usr/bin/ffmpeg"),
                patch("video_tool.processor._run") as run_mock,
            ):
                result = process_video(
                    ProcessingRequest(
                        video_path=video,
                        subtitle_path=None,
                        mode="strip-soft",
                        language_code="zh-Hans",
                    )
                )

            command = run_mock.call_args.args[0]
            self.assertEqual(result.mode, "strip-soft")
            self.assertIn("-0:s?", command)
            self.assertIn("copy", command)
            self.assertTrue(result.output_path.name.endswith(".no-subs.mp4"))

    def test_srt_timestamp_conversion(self) -> None:
        self.assertEqual(_srt_timestamp_seconds("01:02:03,500"), 3723.5)


if __name__ == "__main__":
    unittest.main()
