from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from video_tool.chinese import to_simplified_chinese
from video_tool.paths import media_stem, organized_output_path, output_directory
from video_tool.srt import parse_srt, write_manual_translation
from video_tool.web import render_editor, render_page


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


if __name__ == "__main__":
    unittest.main()
