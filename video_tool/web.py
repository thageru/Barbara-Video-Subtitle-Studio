from __future__ import annotations

import html
import json
import subprocess
import threading
import traceback
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from .chinese import to_simplified_chinese
from .processor import ProcessingError, ProcessingRequest, SubtitleStyle, process_video, render_subtitle_preview
from .paths import organized_output_path
from .srt import default_translated_path, parse_srt, write_manual_translation
from .transcriber import SubtitleGenerationRequest, generate_subtitles
from .translator import TranslationRequest, translate_srt_with_api


@dataclass
class JobRecord:
    id: int
    created_at: str
    status: str
    action: str
    video_path: str = ""
    subtitle_path: str = ""
    mode: str = ""
    languages: str = ""
    output_path: str = ""
    error: str = ""
    command: list[str] | None = None
    details: str = ""


@dataclass
class AppState:
    jobs: list[JobRecord] = field(default_factory=list)
    previews: dict[str, Path] = field(default_factory=dict)
    next_id: int = 1
    lock: threading.Lock = field(default_factory=threading.Lock)


STATE = AppState()


class VideoToolHandler(BaseHTTPRequestHandler):
    server_version = "VideoProcessDemo/0.4"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            query = parse_qs(parsed.query)
            self._send_html(render_page(message=query.get("message", [""])[0]))
            return
        if parsed.path == "/jobs.json":
            with STATE.lock:
                payload = [asdict(job) for job in STATE.jobs]
            self._send_json(payload)
            return
        if parsed.path == "/choose-file":
            query = parse_qs(parsed.query)
            purpose = query.get("purpose", ["file"])[0]
            self._send_json(_choose_file(purpose))
            return
        if parsed.path == "/choose-directory":
            self._send_json(_choose_directory())
            return
        if parsed.path == "/edit":
            query = parse_qs(parsed.query)
            source = query.get("source", [""])[0]
            target = query.get("target", [""])[0]
            prefill = query.get("prefill", [""])[0] == "1"
            self._send_html(render_editor(source, target, prefill=prefill))
            return
        if parsed.path.startswith("/preview/"):
            preview_id = Path(parsed.path).name
            with STATE.lock:
                path = STATE.previews.get(preview_id)
            if not path or not path.is_file():
                self.send_error(404)
                return
            self._send_file(path, "image/png")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/shutdown":
            self._send_html(render_shutdown_page())
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        data = self._read_form()
        if parsed.path == "/preview-frame":
            self._handle_preview(data)
            return
        if parsed.path == "/save-manual":
            self._handle_save_manual(data)
            return
        if parsed.path in {"/generate-english", "/translate-ai", "/finalize", "/process"}:
            job = self._create_job(parsed.path, data)
            with STATE.lock:
                STATE.jobs.insert(0, job)
            threading.Thread(target=_run_job, args=(job.id, data), daemon=True).start()
            self.send_response(303)
            self.send_header("Location", "/?" + urlencode({"job_id": job.id}))
            self.end_headers()
            return
        self.send_error(404)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        return parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)

    def _create_job(self, path: str, data: dict[str, list[str]]) -> JobRecord:
        action = {
            "/generate-english": "generate-english",
            "/translate-ai": "translate-ai",
            "/finalize": "finalize",
            "/process": "legacy-process",
        }[path]
        with STATE.lock:
            job_id = STATE.next_id
            STATE.next_id += 1
        return JobRecord(
            id=job_id,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="queued",
            action=action,
            video_path=_value(data, "video_path"),
            subtitle_path=_value(data, "subtitle_path") or _value(data, "source_srt"),
            mode=_value(data, "mode"),
            languages=_value(data, "target_language") or _value(data, "languages") or "en",
            details=_job_details(action, data),
        )

    def _handle_preview(self, data: dict[str, list[str]]) -> None:
        try:
            path, _command = render_subtitle_preview(
                video_path=Path(_value(data, "video_path")),
                subtitle_path=Path(_value(data, "subtitle_path")),
                timestamp=_float_value(data, "preview_time", 10.0),
                style=_style_from_form(data),
            )
            preview_id = path.name
            with STATE.lock:
                STATE.previews[preview_id] = path
            self._send_json({"ok": True, "url": f"/preview/{preview_id}"})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)})

    def _handle_save_manual(self, data: dict[str, list[str]]) -> None:
        try:
            source = Path(_value(data, "source_srt")).expanduser().resolve()
            requested_output = Path(_value(data, "output_srt")).expanduser()
            output = organized_output_path(source, requested_output, requested_output.name)
            target_language = _value(data, "target_language") or "zh-Hans"
            bilingual = _value(data, "format") == "bilingual"
            entries = parse_srt(source)
            translations = data.get("translation", [])
            if len(entries) != len(translations):
                raise ProcessingError(f"translation count mismatch: expected {len(entries)}, got {len(translations)}")
            if target_language == "zh-Hans":
                translations = [to_simplified_chinese(item) for item in translations]
            write_manual_translation(entries, translations, output, bilingual=bilingual)
            self.send_response(303)
            self.send_header("Location", "/?" + urlencode({"saved": str(output)}))
            self.end_headers()
        except Exception as exc:
            self._send_html(render_error_page(str(exc), traceback.format_exc()))

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _choose_file(purpose: str) -> dict[str, str | bool]:
    labels = {
        "video": "Select a local video file",
        "subtitle": "Select a local subtitle file",
        "file": "Select a local file",
    }
    prompt = labels.get(purpose, labels["file"])
    script = f"POSIX path of (choose file with prompt {_applescript_string(prompt)})"
    return _run_osascript(script)


def _choose_directory() -> dict[str, str | bool]:
    script = "POSIX path of (choose folder with prompt \"Select an output directory\")"
    return _run_osascript(script)


def _run_osascript(script: str) -> dict[str, str | bool]:
    try:
        process = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if process.returncode != 0:
        error = process.stderr.strip() or "file chooser was cancelled"
        return {"ok": False, "error": error}
    return {"ok": True, "path": process.stdout.strip()}


def _applescript_string(value: str) -> str:
    return json.dumps(value)


def _run_job(job_id: int, data: dict[str, list[str]]) -> None:
    job = _find_job(job_id)
    if job is None:
        return
    _update_job(job_id, status="running")
    try:
        if job.action == "generate-english":
            _run_generate_english(job_id, data)
        elif job.action == "translate-ai":
            _run_translate_ai(job_id, data)
        elif job.action == "finalize":
            _run_finalize(job_id, data)
        else:
            _run_legacy_process(job_id, data)
    except (ProcessingError, OSError, ValueError) as exc:
        _update_job(job_id, status="failed", error=str(exc))
    except Exception as exc:
        _update_job(job_id, status="failed", error=f"{exc}\n{traceback.format_exc()}")


def _run_generate_english(job_id: int, data: dict[str, list[str]]) -> None:
    video = Path(_value(data, "video_path")).expanduser()
    subtitle_dir = Path(_value(data, "subtitle_dir")).expanduser() if _value(data, "subtitle_dir") else None
    results = generate_subtitles(
        SubtitleGenerationRequest(
            video_path=video,
            language_codes=["en"],
            subtitle_dir=subtitle_dir,
            subtitle_basename=_value(data, "subtitle_name") or None,
            model=_value(data, "model") or "small",
            source_language="en",
            overwrite=True,
        )
    )
    result = results[0]
    _update_job(
        job_id,
        status="done",
        output_path=str(result.subtitle_path),
        command=result.command,
        details=f"entries={result.entries}",
    )


def _run_translate_ai(job_id: int, data: dict[str, list[str]]) -> None:
    source = Path(_value(data, "source_srt"))
    requested_output = Path(_value(data, "output_srt"))
    output = organized_output_path(source, requested_output, requested_output.name)
    result = translate_srt_with_api(
        TranslationRequest(
            source_srt=source,
            output_srt=output,
            target_language=_value(data, "target_language") or "zh-Hans",
            base_url=_value(data, "base_url"),
            api_key=_value(data, "api_key"),
            model=_value(data, "model") or "gpt-4.1-mini",
            chunk_size=_int_value(data, "chunk_size", 20),
            glossary=_value(data, "glossary"),
        )
    )
    _update_job(job_id, status="done", output_path=str(result.output_srt), details=f"entries={result.entries}, batches={result.batches}")


def _run_finalize(job_id: int, data: dict[str, list[str]]) -> None:
    result = process_video(
        ProcessingRequest(
            video_path=Path(_value(data, "video_path")),
            subtitle_path=Path(_value(data, "subtitle_path")),
            mode=_value(data, "mode") or "burn",
            language_code=_value(data, "target_language") or "zh-Hans",
            output_path=Path(_value(data, "output_video")).expanduser() if _value(data, "output_video") else None,
            style=_style_from_form(data),
        )
    )
    _update_job(job_id, status="done", output_path=str(result.output_path), command=result.command)


def _run_legacy_process(job_id: int, data: dict[str, list[str]]) -> None:
    languages = [item.strip() for item in data.get("languages", []) if item.strip()] or ["zh-Hans"]
    subtitle_dir = Path(_value(data, "subtitle_dir")).expanduser() if _value(data, "subtitle_dir") else None
    results = generate_subtitles(
        SubtitleGenerationRequest(
            video_path=Path(_value(data, "video_path")).expanduser(),
            language_codes=languages,
            subtitle_dir=subtitle_dir,
            subtitle_basename=_value(data, "subtitle_name") or None,
            burn=_value(data, "mode") == "burn",
            style=_style_from_form(data),
        )
    )
    outputs: list[str] = []
    command: list[str] | None = None
    for result in results:
        outputs.append(str(result.subtitle_path))
        if result.hardsub_path:
            outputs.append(str(result.hardsub_path))
        command = result.command
    _update_job(job_id, status="done", output_path="\n".join(outputs), command=command)


def _find_job(job_id: int) -> JobRecord | None:
    with STATE.lock:
        for job in STATE.jobs:
            if job.id == job_id:
                return job
    return None


def _update_job(job_id: int, **changes: object) -> None:
    with STATE.lock:
        for job in STATE.jobs:
            if job.id == job_id:
                for key, value in changes.items():
                    setattr(job, key, value)
                return


def _value(data: dict[str, list[str]], name: str) -> str:
    return data.get(name, [""])[0].strip()


def _int_value(data: dict[str, list[str]], name: str, default: int) -> int:
    try:
        return int(_value(data, name))
    except ValueError:
        return default


def _float_value(data: dict[str, list[str]], name: str, default: float) -> float:
    try:
        return float(_value(data, name))
    except ValueError:
        return default


def _style_from_form(data: dict[str, list[str]]) -> SubtitleStyle:
    return SubtitleStyle(font_size=_int_value(data, "font_size", 22), y_percent=_float_value(data, "subtitle_y", 2.0))


def _job_details(action: str, data: dict[str, list[str]]) -> str:
    if action == "translate-ai":
        base_url = _value(data, "base_url")
        model = _value(data, "model")
        return f"model={model}, base_url={base_url}, api_key={'set' if _value(data, 'api_key') else 'empty'}"
    if action == "finalize":
        return f"font_size={_value(data, 'font_size') or '22'}, subtitle_y={_value(data, 'subtitle_y') or '2'}%"
    return ""


def render_page(message: str = "") -> str:
    with STATE.lock:
        rows = "\n".join(render_job_row(job) for job in STATE.jobs)
    if not rows:
        rows = '<tr><td colspan="9" class="muted" data-i18n data-en="No jobs yet." data-zh="暂无任务。">No jobs yet.</td></tr>'
    message_html = f'<div id="job-notice" class="notice">{html.escape(message)}</div>' if message else '<div id="job-notice" class="notice" hidden></div>'
    return PAGE_TEMPLATE.replace("__MESSAGE__", message_html).replace("__ROWS__", rows)


def render_editor(source: str, target: str, prefill: bool = False) -> str:
    if not source:
        return render_error_page("Missing source SRT path", "")
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        return render_error_page(f"Source SRT does not exist: {source_path}", "")
    requested_target = Path(target).expanduser() if target else default_translated_path(source_path)
    target_path = organized_output_path(source_path, requested_target, requested_target.name)
    entries = parse_srt(source_path)
    rows = []
    for entry in entries:
        rows.append(
            "<tr>"
            f"<td>{entry.index}</td>"
            f"<td><code>{html.escape(entry.timecode)}</code></td>"
            f"<td>{html.escape(entry.text).replace(chr(10), '<br>')}</td>"
            f"<td><textarea name=\"translation\" rows=\"3\" data-i18n-placeholder data-en=\"Enter subtitle text\" data-zh=\"填写字幕文本\">{html.escape(entry.text) if prefill else ''}</textarea></td>"
            "</tr>"
        )
    return EDITOR_TEMPLATE.replace("__SOURCE__", html.escape(str(source_path))).replace(
        "__TARGET__", html.escape(str(target_path))
    ).replace("__ROWS__", "\n".join(rows)).replace("__COUNT__", str(len(entries))).replace(
        "__EDITOR_TITLE_EN__", "Edit Existing Subtitle" if prefill else "Manual Subtitle Translation"
    ).replace("__EDITOR_TITLE_ZH__", "在线编辑已有字幕" if prefill else "手动字幕翻译")


def render_error_page(message: str, details: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Error</title></head>
<body><main><h1>Error</h1><p>{html.escape(message)}</p><pre>{html.escape(details)}</pre><p><a href="/">Back</a></p></main></body></html>"""


def render_shutdown_page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Service stopped</title></head>
<body><h1>Service stopped</h1><p>The local Python listener is shutting down. You can close this tab.</p></body></html>"""


def render_job_row(job: JobRecord) -> str:
    status_class = f"status-{html.escape(job.status)}"
    return """
<tr>
  <td>{id}</td>
  <td class="{status_class}">{status}</td>
  <td>{action}</td>
  <td>{mode}</td>
  <td>{languages}</td>
  <td><code>{video}</code></td>
  <td><code>{subtitle}</code></td>
  <td><code>{output}</code><div class="muted">{details}</div></td>
  <td><code>{error}</code></td>
</tr>
""".format(
        id=job.id,
        status_class=status_class,
        status=html.escape(job.status),
        action=html.escape(job.action),
        mode=html.escape(job.mode),
        languages=html.escape(job.languages),
        video=html.escape(job.video_path),
        subtitle=html.escape(job.subtitle_path),
        output=html.escape(job.output_path),
        details=html.escape(job.details),
        error=html.escape(job.error),
    )


PAGE_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VideoProcessDemo</title>
  <style>
    :root { --bg: #f5efe4; --ink: #18201c; --muted: #6d746f; --card: #fffaf0; --line: #d7c8ad; --accent: #c24b2c; --accent-2: #1f6b58; --danger: #9c2f25; --shadow: 0 18px 50px rgba(64, 42, 20, .14); }
    * { box-sizing: border-box; }
    body { margin: 0; background: radial-gradient(circle at top left, #f9d999, transparent 34rem), var(--bg); color: var(--ink); font-family: Avenir Next, Charter, Georgia, sans-serif; }
    main { width: min(1180px, calc(100vw - 32px)); margin: 36px auto; }
    .hero { display: grid; gap: 10px; margin-bottom: 24px; }
    .topline { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
    .hero-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    h1 { margin: 0; font-size: clamp(34px, 6vw, 68px); letter-spacing: 0; line-height: 1; }
    h2 { margin: 0 0 12px; }
    .hero p, .hint, .muted { color: var(--muted); }
    .panel { background: color-mix(in srgb, var(--card) 92%, white); border: 1px solid var(--line); border-radius: 24px; box-shadow: var(--shadow); padding: 22px; margin-bottom: 22px; }
    form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    label { display: grid; gap: 7px; font-weight: 700; }
    input, select, textarea { width: 100%; border: 1px solid var(--line); border-radius: 14px; padding: 12px 13px; font: inherit; background: #fffdf8; color: var(--ink); }
    textarea { min-height: 92px; }
    .path-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
    .full { grid-column: 1 / -1; }
    .actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    button { border: 0; border-radius: 999px; padding: 12px 18px; background: var(--accent); color: white; font-weight: 800; cursor: pointer; }
    button.secondary { background: var(--accent-2); }
    button.ghost { background: transparent; color: var(--ink); border: 1px solid var(--line); }
    button.danger { background: var(--danger); }
    .notice { background: #e8f4ee; color: var(--accent-2); border: 1px solid #b8dacd; padding: 12px 14px; border-radius: 8px; margin-bottom: 16px; }
    .notice.failed { background: #fff0ea; color: var(--danger); border-color: #efc0b1; }
    .toast { position: fixed; top: 18px; right: 18px; z-index: 20; width: min(420px, calc(100vw - 36px)); box-shadow: var(--shadow); }
    .error-note { display: none; background: #fff0ea; color: var(--danger); border: 1px solid #efc0b1; padding: 12px 14px; border-radius: 16px; margin-bottom: 16px; }
    .preview { display: grid; gap: 12px; }
    .preview img { max-width: 100%; border-radius: 18px; border: 1px solid var(--line); background: #111; }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { border-bottom: 1px solid var(--line); padding: 10px; text-align: left; vertical-align: top; font-size: 14px; }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    code { white-space: pre-wrap; word-break: break-all; font-family: Menlo, Consolas, monospace; font-size: 12px; }
    .status-done { color: var(--accent-2); font-weight: 800; }
    .status-failed { color: var(--accent); font-weight: 800; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    @media (max-width: 760px) { form, .grid-3 { grid-template-columns: 1fr; } .topline { display: grid; } .hero-actions { justify-content: flex-start; } .path-row { grid-template-columns: 1fr; } table { display: block; overflow-x: auto; } }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="topline">
        <div>
          <h1 data-i18n data-en="Local Video Subtitle Processor" data-zh="本地视频字幕处理器">本地视频字幕处理器</h1>
          <p data-i18n data-en="Generate English SRT first, then translate with an OpenAI-compatible endpoint or manually edit Chinese subtitles. Files stay local unless you use an API endpoint." data-zh="先生成英文 SRT，再通过 OpenAI-compatible 端点翻译，或手动编辑中文字幕。除非使用 API 端点，否则文件始终保留在本地。">先生成英文 SRT，再通过 OpenAI-compatible 端点翻译，或手动编辑中文字幕。除非使用 API 端点，否则文件始终保留在本地。</p>
        </div>
        <div class="hero-actions">
          <button type="button" class="ghost" id="language-toggle" onclick="toggleLanguage()">English</button>
          <button type="button" class="danger" data-i18n data-en="Close Service" data-zh="关闭服务" onclick="shutdownServer()">关闭服务</button>
        </div>
      </div>
    </section>
    __MESSAGE__
    <div id="client-error" class="error-note"></div>

    <section class="panel">
      <h2 data-i18n data-en="1. Generate English SRT" data-zh="1. 生成英文 SRT">1. 生成英文 SRT</h2>
      <form method="post" action="/generate-english">
        <label class="full"><span data-i18n data-en="Video file" data-zh="视频文件">视频文件</span>
          <div class="path-row">
            <input id="video-path" name="video_path" placeholder="选择本地视频文件" data-i18n-placeholder data-en="Choose a local video file" data-zh="选择本地视频文件" required oninput="fillVideoDefaults(this.value)">
            <button type="button" class="secondary" data-i18n data-en="Choose Video" data-zh="选择视频" onclick="choosePath(this, '/choose-file?purpose=video', 'video-path', true, 'video')">选择视频</button>
          </div>
        </label>
        <label><span data-i18n data-en="Output root directory" data-zh="输出根目录">输出根目录</span>
          <div class="path-row">
            <input id="subtitle-dir" name="subtitle_dir" placeholder="默认创建 视频名/ 文件夹" data-i18n-placeholder data-en="Creates a video-name folder by default" data-zh="默认创建 视频名/ 文件夹">
            <button type="button" class="ghost" data-i18n data-en="Choose Folder" data-zh="选择目录" onclick="choosePath(this, '/choose-directory', 'subtitle-dir', false)">选择目录</button>
          </div>
        </label>
        <label><span data-i18n data-en="Subtitle base file name" data-zh="字幕基础文件名">字幕基础文件名</span>
          <input id="subtitle-name" name="subtitle_name" placeholder="默认使用视频文件名" data-i18n-placeholder data-en="Defaults to video file name" data-zh="默认使用视频文件名">
        </label>
        <label><span data-i18n data-en="WhisperKit model" data-zh="WhisperKit 模型">WhisperKit 模型</span>
          <input name="model" value="small">
        </label>
        <div class="actions full">
          <button type="submit" data-i18n data-en="Generate English SRT" data-zh="生成英文 SRT">生成英文 SRT</button>
          <span class="hint" data-i18n data-en="Output: subtitle-name.en.srt" data-zh="输出：字幕名.en.srt">输出：字幕名.en.srt</span>
        </div>
      </form>
    </section>

    <section class="panel">
      <h2 data-i18n data-en="2. Translate English SRT" data-zh="2. 翻译英文 SRT">2. Translate English SRT</h2>
      <form method="post" action="/translate-ai">
        <label class="full"><span data-i18n data-en="English SRT" data-zh="英文 SRT">English SRT</span>
          <div class="path-row">
            <input id="source-srt" name="source_srt" placeholder="Choose .en.srt" data-i18n-placeholder data-en="Choose .en.srt" data-zh="选择 .en.srt" required oninput="fillSrtDefaults(this.value)">
            <button type="button" class="secondary" data-i18n data-en="Choose SRT" data-zh="选择 SRT" onclick="choosePath(this, '/choose-file?purpose=subtitle', 'source-srt', true, 'srt')">选择 SRT</button>
          </div>
        </label>
        <label><span data-i18n data-en="Chinese output SRT" data-zh="中文输出 SRT">Chinese output SRT</span>
          <input id="output-srt" name="output_srt" placeholder="Defaults to source.zh-Hans.srt" data-i18n-placeholder data-en="Defaults to source.zh-Hans.srt" data-zh="默认输出 source.zh-Hans.srt" required>
        </label>
        <label><span data-i18n data-en="Target language" data-zh="目标语言">Target language</span>
          <select name="target_language"><option value="zh-Hans" data-i18n data-en="zh-Hans - Simplified Chinese" data-zh="zh-Hans - 简体中文">zh-Hans - Simplified Chinese</option><option value="en" data-i18n data-en="en - English" data-zh="en - 英文">en - English</option></select>
        </label>
        <label><span data-i18n data-en="Base URL" data-zh="接口地址 Base URL">Base URL</span>
          <input name="base_url" placeholder="https://api.openai.com/v1 or local /v1" data-i18n-placeholder data-en="https://api.openai.com/v1 or local /v1" data-zh="https://api.openai.com/v1 或本地 /v1">
        </label>
        <label><span data-i18n data-en="API Key" data-zh="API Key">API Key</span>
          <input name="api_key" type="password" autocomplete="off" placeholder="Optional for local endpoints" data-i18n-placeholder data-en="Optional for local endpoints" data-zh="本地端点可留空">
        </label>
        <label><span data-i18n data-en="Model" data-zh="模型">Model</span>
          <input name="model" value="gpt-4.1-mini">
        </label>
        <label><span data-i18n data-en="Batch size" data-zh="批次大小">Batch size</span>
          <input name="chunk_size" type="number" min="5" max="50" value="20">
        </label>
        <label class="full"><span data-i18n data-en="Glossary / translation notes" data-zh="术语表 / 翻译说明">Glossary / translation notes</span>
          <textarea name="glossary" placeholder="Optional glossary. Example: PYP=小学项目, transdisciplinary=超学科" data-i18n-placeholder data-en="Optional glossary. Example: PYP=小学项目, transdisciplinary=超学科" data-zh="可选术语表。例如：PYP=小学项目，transdisciplinary=超学科"></textarea>
        </label>
        <div class="actions full">
          <button type="submit" data-i18n data-en="AI Translate" data-zh="AI 翻译">AI Translate</button>
          <button type="button" class="ghost" data-i18n data-en="Manual Edit Table" data-zh="手动编辑表格" onclick="openManualEditor()">Manual Edit Table</button>
          <span class="hint" data-i18n data-en="Manual edit never calls any API." data-zh="手动编辑不会调用任何 API。">Manual edit never calls any API.</span>
        </div>
      </form>
    </section>

    <section class="panel">
      <h2 data-i18n data-en="3. Preview and Finalize" data-zh="3. 预览并输出">3. Preview and Finalize</h2>
      <form id="finalize-form" method="post" action="/finalize">
        <label class="full"><span data-i18n data-en="Video file" data-zh="视频文件">Video file</span>
          <div class="path-row">
            <input id="final-video" name="video_path" placeholder="Choose a local video file" data-i18n-placeholder data-en="Choose a local video file" data-zh="选择本地视频文件" required oninput="fillFinalOutput()">
            <button type="button" class="secondary" data-i18n data-en="Choose Video" data-zh="选择视频" onclick="choosePath(this, '/choose-file?purpose=video', 'final-video', false, 'final-video')">选择视频</button>
          </div>
        </label>
        <label class="full"><span data-i18n data-en="Subtitle file" data-zh="字幕文件">Subtitle file</span>
          <div class="path-row">
            <input id="final-subtitle" name="subtitle_path" placeholder="Choose translated .srt" data-i18n-placeholder data-en="Choose translated .srt" data-zh="选择翻译后的 .srt" required oninput="fillFinalOutput()">
            <button type="button" class="secondary" data-i18n data-en="Choose Subtitle" data-zh="选择字幕" onclick="choosePath(this, '/choose-file?purpose=subtitle', 'final-subtitle', false, 'final-subtitle')">选择字幕</button>
          </div>
        </label>
        <label><span data-i18n data-en="Finalize mode" data-zh="输出方式">Finalize mode</span>
          <select name="mode" id="final-mode" onchange="fillFinalOutput()">
            <option value="burn" data-i18n data-en="Hard burn into video" data-zh="硬字幕烧录进视频">Hard burn into video</option>
            <option value="external" data-i18n data-en="External sidecar subtitle" data-zh="外挂字幕文件">External sidecar subtitle</option>
          </select>
        </label>
        <label><span data-i18n data-en="Target language" data-zh="目标语言">Target language</span>
          <select name="target_language"><option value="zh-Hans" data-i18n data-en="zh-Hans - Simplified Chinese" data-zh="zh-Hans - 简体中文">zh-Hans - Simplified Chinese</option><option value="en" data-i18n data-en="en - English" data-zh="en - 英文">en - English</option></select>
        </label>
        <label><span data-i18n data-en="Font size" data-zh="字体大小">Font size</span>
          <input id="font-size" name="font_size" type="number" min="8" max="128" value="22">
        </label>
        <label><span data-i18n data-en="Subtitle Y position: bottom margin %" data-zh="字幕 Y 位置：距底部百分比">Subtitle Y position: bottom margin %</span>
          <input id="subtitle-y" name="subtitle_y" type="range" min="0" max="100" value="2" oninput="subtitleYValue.textContent = this.value + '%'">
          <span class="hint" id="subtitleYValue">2%</span>
        </label>
        <label><span data-i18n data-en="Preview timestamp seconds" data-zh="预览时间点（秒）">Preview timestamp seconds</span>
          <input id="preview-time" name="preview_time" type="number" min="0" step="0.1" value="10">
        </label>
        <label><span data-i18n data-en="Output video / subtitle path" data-zh="输出视频 / 字幕路径">Output video / subtitle path</span>
          <input id="output-video" name="output_video" placeholder="Optional exact output path" data-i18n-placeholder data-en="Optional exact output path" data-zh="可选：指定完整输出路径" oninput="this.dataset.auto='false'">
        </label>
        <div class="actions full">
          <button type="button" class="secondary" data-i18n data-en="Capture Preview Frame" data-zh="截取预览帧" onclick="previewFrame()">Capture Preview Frame</button>
          <button type="submit" data-i18n data-en="Finalize" data-zh="开始输出">Finalize</button>
          <span class="hint" data-i18n data-en="Preview and hard burn use the same font/position style." data-zh="预览和硬烧录使用同一套字体/位置样式。">Preview and hard burn use the same font/position style.</span>
        </div>
      </form>
      <div class="preview full" id="preview-box"></div>
    </section>

    <section class="panel">
      <h2 data-i18n data-en="Edit Existing Subtitle" data-zh="在线编辑已有字幕">在线编辑已有字幕</h2>
      <form onsubmit="openExistingEditor(event)">
        <label class="full"><span data-i18n data-en="Subtitle file" data-zh="字幕文件">字幕文件</span>
          <div class="path-row">
            <input id="edit-subtitle" placeholder="选择要编辑的 .srt" data-i18n-placeholder data-en="Choose an existing .srt" data-zh="选择要编辑的 .srt" required>
            <button type="button" class="secondary" data-i18n data-en="Choose Subtitle" data-zh="选择字幕" onclick="choosePath(this, '/choose-file?purpose=subtitle', 'edit-subtitle', false)">选择字幕</button>
          </div>
        </label>
        <div class="actions full">
          <button type="submit" data-i18n data-en="Open Online Editor" data-zh="打开在线编辑器">打开在线编辑器</button>
          <span class="hint" data-i18n data-en="Edit text while preserving subtitle indexes and timing." data-zh="修改字幕文本，同时保留序号和时间轴。">修改字幕文本，同时保留序号和时间轴。</span>
        </div>
      </form>
    </section>

    <section class="panel">
      <h2 data-i18n data-en="Jobs" data-zh="任务列表">Jobs</h2>
      <table>
        <thead><tr><th>ID</th><th data-i18n data-en="Status" data-zh="状态">Status</th><th data-i18n data-en="Action" data-zh="操作">Action</th><th data-i18n data-en="Mode" data-zh="模式">Mode</th><th data-i18n data-en="Language" data-zh="语言">Language</th><th data-i18n data-en="Video" data-zh="视频">Video</th><th data-i18n data-en="Subtitle" data-zh="字幕">Subtitle</th><th data-i18n data-en="Output" data-zh="输出">Output</th><th data-i18n data-en="Error" data-zh="错误">Error</th></tr></thead>
        <tbody id="jobs-body">__ROWS__</tbody>
      </table>
    </section>
  </main>
  <script>
    const STATIC_COPY = {
      en: {
        switchLabel: '中文', choosing: 'Choosing...', chooseEnglishFirst: 'Choose an English SRT first.',
        renderingPreview: 'Rendering preview...', previewFailed: 'preview failed', noJobs: 'No jobs yet.',
        stopConfirm: 'Stop the local Python web service now?', stoppedTitle: 'Service stopped',
        stoppedBody: 'The local Python listener has been shut down. You can close this tab.', previewAlt: 'subtitle preview frame',
        jobStarted: 'Job {id} started.', jobDone: 'Job {id} completed.', jobFailed: 'Job {id} failed: {error}', saved: 'Subtitle saved: {path}'
      },
      zh: {
        switchLabel: 'English', choosing: '选择中...', chooseEnglishFirst: '请先选择英文 SRT。',
        renderingPreview: '正在生成预览...', previewFailed: '预览失败', noJobs: '暂无任务。',
        stopConfirm: '现在停止本地 Python Web 服务吗？', stoppedTitle: '服务已停止',
        stoppedBody: '本地 Python 监听服务已关闭。可以关闭此页面。', previewAlt: '字幕预览帧',
        jobStarted: '任务 {id} 已开始。', jobDone: '任务 {id} 已完成。', jobFailed: '任务 {id} 失败：{error}', saved: '字幕已保存：{path}'
      }
    };
    const CODE_COPY = {
      status: {
        queued: { en: 'queued', zh: '排队中' }, running: { en: 'running', zh: '运行中' },
        done: { en: 'done', zh: '完成' }, failed: { en: 'failed', zh: '失败' }
      },
      action: {
        'generate-english': { en: 'generate English', zh: '生成英文' }, 'translate-ai': { en: 'AI translate', zh: 'AI 翻译' },
        finalize: { en: 'finalize', zh: '输出' }, 'legacy-process': { en: 'legacy process', zh: '旧流程处理' }
      },
      mode: {
        burn: { en: 'burn', zh: '硬烧录' }, external: { en: 'external', zh: '外挂字幕' }
      }
    };
    const LANGUAGE_STORAGE_KEY = 'vpd-ui-language-v2';
    let currentLanguage = localStorage.getItem(LANGUAGE_STORAGE_KEY) || 'zh';
    const knownJobStatuses = new Map();
    let watchedJobId = Number(new URLSearchParams(window.location.search).get('job_id') || 0);

    function uiText(key) {
      return (STATIC_COPY[currentLanguage] && STATIC_COPY[currentLanguage][key]) || STATIC_COPY.en[key] || key;
    }

    function formatText(key, values) {
      return Object.entries(values || {}).reduce((text, [name, value]) => text.replace(`{${name}}`, value), uiText(key));
    }

    function showNotice(message, failed = false, toast = false) {
      const box = document.getElementById('job-notice');
      box.textContent = message;
      box.hidden = false;
      box.classList.toggle('failed', failed);
      box.classList.toggle('toast', toast);
      if (toast) setTimeout(() => box.classList.remove('toast'), 6000);
    }

    function labelFor(group, value) {
      const row = CODE_COPY[group] && CODE_COPY[group][value];
      return row ? row[currentLanguage] || row.en : value;
    }

    function applyLanguage(language) {
      currentLanguage = language === 'zh' ? 'zh' : 'en';
      localStorage.setItem(LANGUAGE_STORAGE_KEY, currentLanguage);
      document.documentElement.lang = currentLanguage === 'zh' ? 'zh-CN' : 'en';
      document.querySelectorAll('[data-i18n]').forEach((node) => {
        node.textContent = node.dataset[currentLanguage] || node.dataset.en || node.textContent;
      });
      document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
        node.placeholder = node.dataset[currentLanguage] || node.dataset.en || node.placeholder;
      });
      const toggle = document.getElementById('language-toggle');
      if (toggle) toggle.textContent = uiText('switchLabel');
      refreshJobs();
    }

    function toggleLanguage() {
      applyLanguage(currentLanguage === 'zh' ? 'en' : 'zh');
    }

    function showError(message) {
      const box = document.getElementById('client-error');
      box.textContent = message;
      box.style.display = 'block';
    }

    async function choosePath(button, endpoint, inputId, updateDefaults, type) {
      const original = button.textContent;
      button.disabled = true;
      button.textContent = uiText('choosing');
      try {
        const response = await fetch(endpoint);
        const payload = await response.json();
        if (payload.ok && payload.path) {
          document.getElementById(inputId).value = payload.path;
          if (updateDefaults && type === 'video') fillVideoDefaults(payload.path);
          if (updateDefaults && type === 'srt') fillSrtDefaults(payload.path);
          if (type === 'final-video' || type === 'final-subtitle') fillFinalOutput();
          document.getElementById('client-error').style.display = 'none';
        } else if (payload.error) {
          showError(payload.error);
        }
      } catch (error) {
        showError(String(error));
      } finally {
        button.disabled = false;
        button.textContent = original;
      }
    }

    function splitPath(path) {
      const normalized = String(path || '').split('\\\\').join('/');
      const slash = normalized.lastIndexOf('/');
      const dir = slash >= 0 ? normalized.slice(0, slash) : '';
      const file = slash >= 0 ? normalized.slice(slash + 1) : normalized;
      const dot = file.lastIndexOf('.');
      const stem = dot > 0 ? file.slice(0, dot) : file;
      return { dir, file, stem };
    }

    function fillVideoDefaults(videoPath) {
      const parts = splitPath(videoPath);
      if (!parts.file) return;
      const dirInput = document.getElementById('subtitle-dir');
      const nameInput = document.getElementById('subtitle-name');
      if (!dirInput.value && parts.dir) dirInput.value = parts.dir + '/' + parts.stem;
      if (!nameInput.value && parts.stem) nameInput.value = parts.stem;
      document.getElementById('final-video').value = videoPath;
      fillFinalOutput();
    }

    function fillSrtDefaults(sourcePath) {
      if (!sourcePath) return;
      let target = sourcePath;
      if (target.endsWith('.en.srt')) target = target.slice(0, -7) + '.zh-Hans.srt';
      else if (target.endsWith('.srt')) target = target.slice(0, -4) + '.zh-Hans.srt';
      else target += '.zh-Hans.srt';
      const output = document.getElementById('output-srt');
      if (!output.value) output.value = target;
      document.getElementById('final-subtitle').value = output.value || target;
      fillFinalOutput();
    }

    function fillFinalOutput() {
      const video = document.getElementById('final-video').value;
      const subtitle = document.getElementById('final-subtitle').value;
      const out = document.getElementById('output-video');
      if (!video || !subtitle) return;
      if (out.value && out.dataset.auto === 'false') return;
      const v = splitPath(video);
      const suffix = document.getElementById('final-mode').value === 'burn' ? '.zh-Hans.hardsub.mp4' : '.zh-Hans.srt';
      out.value = (v.dir ? v.dir + '/' : '') + v.stem + '/' + v.stem + suffix;
      out.dataset.auto = 'true';
    }

    function openManualEditor() {
      const source = document.getElementById('source-srt').value;
      const target = document.getElementById('output-srt').value;
      if (!source) { showError(uiText('chooseEnglishFirst')); return; }
      window.location.href = '/edit?' + new URLSearchParams({ source, target }).toString();
    }

    function openExistingEditor(event) {
      event.preventDefault();
      const source = document.getElementById('edit-subtitle').value;
      if (!source) return;
      window.location.href = '/edit?' + new URLSearchParams({ source, target: source, prefill: '1' }).toString();
    }

    async function previewFrame() {
      const form = document.getElementById('finalize-form');
      const data = new URLSearchParams(new FormData(form));
      const box = document.getElementById('preview-box');
      box.innerHTML = `<p class="muted">${uiText('renderingPreview')}</p>`;
      try {
        const response = await fetch('/preview-frame', { method: 'POST', body: data });
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || uiText('previewFailed'));
        box.innerHTML = `<img src="${payload.url}?t=${Date.now()}" alt="${uiText('previewAlt')}">`;
      } catch (error) {
        box.innerHTML = '';
        showError(String(error));
      }
    }

    async function refreshJobs() {
      try {
        const response = await fetch('/jobs.json');
        const jobs = await response.json();
        const body = document.getElementById('jobs-body');
        if (!jobs.length) {
          body.innerHTML = `<tr><td colspan="9" class="muted">${uiText('noJobs')}</td></tr>`;
          return;
        }
        body.innerHTML = jobs.map(renderJob).join('');
        jobs.forEach((job) => {
          const previous = knownJobStatuses.get(job.id);
          knownJobStatuses.set(job.id, job.status);
          if (job.status === 'done' && ((previous && previous !== 'done') || watchedJobId === job.id)) {
            showNotice(formatText('jobDone', { id: job.id }), false, true);
            watchedJobId = 0;
          } else if (job.status === 'failed' && ((previous && previous !== 'failed') || watchedJobId === job.id)) {
            showNotice(formatText('jobFailed', { id: job.id, error: job.error || '' }), true, true);
            watchedJobId = 0;
          }
        });
      } catch (error) {
        console.warn(error);
      }
    }

    function renderJob(job) {
      const statusClass = `status-${escapeHtml(job.status)}`;
      return `<tr>
        <td>${job.id}</td>
        <td class="${statusClass}">${escapeHtml(labelFor('status', job.status))}</td>
        <td>${escapeHtml(labelFor('action', job.action))}</td>
        <td>${escapeHtml(labelFor('mode', job.mode))}</td>
        <td>${escapeHtml(job.languages)}</td>
        <td><code>${escapeHtml(job.video_path || '')}</code></td>
        <td><code>${escapeHtml(job.subtitle_path || '')}</code></td>
        <td><code>${escapeHtml(job.output_path || '')}</code><div class="muted">${escapeHtml(job.details || '')}</div></td>
        <td><code>${escapeHtml(job.error || '')}</code></td>
      </tr>`;
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[char]));
    }

    async function shutdownServer() {
      if (!confirm(uiText('stopConfirm'))) return;
      try {
        await fetch('/shutdown', { method: 'POST' });
      } finally {
        document.body.innerHTML = `<main><section class="panel"><h1>${uiText('stoppedTitle')}</h1><p>${uiText('stoppedBody')}</p></section></main>`;
        window.close();
      }
    }

    const pageParams = new URLSearchParams(window.location.search);
    if (watchedJobId) showNotice(formatText('jobStarted', { id: watchedJobId }));
    if (pageParams.get('saved')) showNotice(formatText('saved', { path: pageParams.get('saved') }));
    applyLanguage(currentLanguage);
    refreshJobs();
    setInterval(refreshJobs, 5000);
  </script>
</body>
</html>"""


EDITOR_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manual Subtitle Translation</title>
  <style>
    body { margin: 0; background: #f5efe4; color: #18201c; font-family: Avenir Next, Charter, Georgia, sans-serif; }
    main { width: min(1280px, calc(100vw - 32px)); margin: 28px auto; }
    .panel { background: #fffaf0; border: 1px solid #d7c8ad; border-radius: 22px; padding: 20px; box-shadow: 0 18px 50px rgba(64, 42, 20, .14); }
    .top { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
    .top-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    input, select, textarea { width: 100%; border: 1px solid #d7c8ad; border-radius: 12px; padding: 10px; font: inherit; background: #fffdf8; }
    textarea { min-width: 320px; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border-bottom: 1px solid #d7c8ad; padding: 8px; vertical-align: top; }
    th { color: #6d746f; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    code { white-space: pre-wrap; word-break: break-all; font-family: Menlo, Consolas, monospace; font-size: 12px; }
    button { border: 0; border-radius: 999px; padding: 12px 18px; background: #c24b2c; color: white; font-weight: 800; cursor: pointer; }
    button.ghost { background: transparent; color: #18201c; border: 1px solid #d7c8ad; }
    a { color: #1f6b58; font-weight: 800; }
  </style>
</head>
<body>
  <main>
    <form class="panel" method="post" action="/save-manual">
      <div class="top">
        <div>
          <h1 data-i18n data-en="__EDITOR_TITLE_EN__" data-zh="__EDITOR_TITLE_ZH__">__EDITOR_TITLE_ZH__</h1>
          <p data-i18n data-en="Subtitle entries: __COUNT__. Edit text without changing indexes or timing." data-zh="字幕条数：__COUNT__。可修改文本，序号和时间轴保持不变。">字幕条数：__COUNT__。可修改文本，序号和时间轴保持不变。</p>
        </div>
        <div class="top-actions">
          <button type="button" class="ghost" id="language-toggle" onclick="toggleLanguage()">English</button>
          <a href="/" data-i18n data-en="Back" data-zh="返回">返回</a>
        </div>
      </div>
      <p><strong data-i18n data-en="Subtitle:" data-zh="字幕文件：">字幕文件：</strong> <code>__SOURCE__</code></p>
      <input type="hidden" name="source_srt" value="__SOURCE__">
      <label><span data-i18n data-en="Output SRT" data-zh="输出 SRT">Output SRT</span>
        <input name="output_srt" value="__TARGET__" required>
      </label>
      <label><span data-i18n data-en="Target language" data-zh="目标语言">Target language</span>
        <select name="target_language"><option value="zh-Hans" data-i18n data-en="zh-Hans - Simplified Chinese" data-zh="zh-Hans - 简体中文">zh-Hans - Simplified Chinese</option><option value="en" data-i18n data-en="en - English" data-zh="en - 英文">en - English</option></select>
      </label>
      <label><span data-i18n data-en="Export format" data-zh="导出格式">Export format</span>
        <select name="format"><option value="pure" data-i18n data-en="Pure translated subtitle" data-zh="纯翻译字幕">Pure translated subtitle</option><option value="bilingual" data-i18n data-en="Bilingual: English + translation" data-zh="双语：英文 + 译文">Bilingual: English + translation</option></select>
      </label>
      <table>
        <thead><tr><th>#</th><th data-i18n data-en="Timecode" data-zh="时间码">Timecode</th><th data-i18n data-en="Current text" data-zh="当前文本">当前文本</th><th data-i18n data-en="Edited text" data-zh="编辑后文本">编辑后文本</th></tr></thead>
        <tbody>__ROWS__</tbody>
      </table>
      <p><button type="submit" data-i18n data-en="Save SRT" data-zh="保存 SRT">Save SRT</button></p>
    </form>
  </main>
  <script>
    const LANGUAGE_STORAGE_KEY = 'vpd-ui-language-v2';
    let currentLanguage = localStorage.getItem(LANGUAGE_STORAGE_KEY) || 'zh';
    function applyLanguage(language) {
      currentLanguage = language === 'zh' ? 'zh' : 'en';
      localStorage.setItem(LANGUAGE_STORAGE_KEY, currentLanguage);
      document.documentElement.lang = currentLanguage === 'zh' ? 'zh-CN' : 'en';
      document.querySelectorAll('[data-i18n]').forEach((node) => {
        node.textContent = node.dataset[currentLanguage] || node.dataset.en || node.textContent;
      });
      document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
        node.placeholder = node.dataset[currentLanguage] || node.dataset.en || node.placeholder;
      });
      const toggle = document.getElementById('language-toggle');
      if (toggle) toggle.textContent = currentLanguage === 'zh' ? 'English' : '中文';
    }
    function toggleLanguage() {
      applyLanguage(currentLanguage === 'zh' ? 'en' : 'zh');
    }
    applyLanguage(currentLanguage);
  </script>
</body>
</html>"""


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    server = ThreadingHTTPServer((host, port), VideoToolHandler)
    url = f"http://{host}:{port}/"
    print(f"VideoProcessDemo web UI: {url}")
    print("Press Ctrl+C to stop, or click Close Service in the browser.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        print("VideoProcessDemo web UI stopped.")
