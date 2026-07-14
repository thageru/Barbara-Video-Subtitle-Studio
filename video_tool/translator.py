from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .chinese import to_simplified_chinese
from .processor import ProcessingError
from .srt import SrtEntry, is_non_speech_text, parse_srt, parse_srt_text, write_srt


@dataclass(frozen=True)
class TranslationRequest:
    source_srt: Path
    output_srt: Path
    target_language: str = "zh-Hans"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    chunk_size: int = 20
    temperature: float = 0.1
    glossary: str = ""


@dataclass(frozen=True)
class TranslationResult:
    output_srt: Path
    entries: int
    batches: int


def translate_srt_with_api(request: TranslationRequest) -> TranslationResult:
    source = Path(request.source_srt).expanduser().resolve()
    output = Path(request.output_srt).expanduser().resolve()
    if not source.is_file():
        raise ProcessingError(f"English SRT does not exist: {source}")
    if not request.base_url.strip():
        raise ProcessingError("AI translation requires a base URL")
    if not request.model.strip():
        raise ProcessingError("AI translation requires a model name")

    entries = parse_srt(source)
    if not entries:
        raise ProcessingError(f"no SRT entries found: {source}")

    translations: list[str] = []
    batches = list(_chunked(entries, max(1, request.chunk_size)))
    for batch_no, batch in enumerate(batches, start=1):
        prompt = _build_prompt(batch_no, batch, request.target_language, request.glossary)
        raw = _call_chat(
            base_url=request.base_url,
            api_key=request.api_key,
            model=request.model,
            prompt=prompt,
            temperature=request.temperature,
        )
        parsed = _parse_translation_json(raw)
        batch_translations = parsed.get("translations")
        if not isinstance(batch_translations, list) or len(batch_translations) != len(batch):
            raise ProcessingError(f"batch {batch_no} returned {len(batch_translations or [])} translations, expected {len(batch)}")
        for item in batch_translations:
            text = str(item).strip()
            if request.target_language == "zh-Hans":
                text = to_simplified_chinese(text)
            translations.append(text)

    write_srt(entries, translations, output)
    return TranslationResult(output_srt=output, entries=len(entries), batches=len(batches))


def _chunked(items: list[SrtEntry], size: int) -> list[list[SrtEntry]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_prompt(batch_no: int, entries: list[SrtEntry], target_language: str, glossary: str) -> str:
    lines = [
        f"Translate this subtitle batch to {target_language}.",
        "Return JSON only in this exact shape:",
        f'{ {"batch": batch_no, "translations": ["..."]} }'.replace("'", '"'),
        "Rules: preserve meaning, make subtitles natural and concise, keep exactly one translation per input item, no timestamps, no markdown.",
    ]
    if target_language == "zh-Hans":
        lines.append("Use Simplified Chinese only; do not output Traditional Chinese characters.")
    if glossary.strip():
        lines.extend(["Glossary:", glossary.strip()])
    lines.append("Items:")
    for entry in entries:
        text = " ".join(entry.text.splitlines())
        lines.append(f"{entry.index}. {text}")
    return "\n".join(lines) + "\n"


def _speech_entries(source: Path) -> list[SrtEntry]:
    speech = [entry for entry in parse_srt(source) if not is_non_speech_text(entry.text)]
    return [SrtEntry(index=index, timecode=entry.timecode, text=entry.text) for index, entry in enumerate(speech, start=1)]


def build_webchat_prompt(source_srt: Path, target_language: str = "zh-Hans", chunk_size: int = 20, glossary: str = "") -> tuple[str, int, int]:
    del chunk_size
    source = Path(source_srt).expanduser().resolve()
    if not source.is_file():
        raise ProcessingError(f"English SRT does not exist: {source}")
    entries = _speech_entries(source)
    if not entries:
        raise ProcessingError(f"no speech subtitle entries found: {source}")
    target_label = "简体中文（zh-Hans）" if target_language == "zh-Hans" else target_language
    source_blocks = ["\n".join([str(entry.index), entry.timecode, entry.text]) for entry in entries]
    lines = [
        "你是一名专业的视频字幕译者。请将下面的英文 SRT 字幕翻译为" + target_label + "。",
        "",
        "翻译要求：",
        "1. 准确理解上下文，使用自然、简洁、适合屏幕阅读的字幕表达。",
        "2. 保留人名、数字、专有名词和语气；不要遗漏、合并、拆分或编造内容。",
        "3. 英文来自语音识别。只有在上下文非常明确时才修正明显识别或标点错误。",
        "4. 每个字幕块只翻译正文，不得修改序号和时间码。",
        "5. 返回的字幕块数量、顺序、序号和时间码必须与输入完全一致。",
        "6. 只返回完整 SRT 正文，不要解释，不要总结，不要添加 Markdown 代码块。",
    ]
    if target_language == "zh-Hans":
        lines.append("7. 仅使用简体中文，不得混入繁体中文。")
    if glossary.strip():
        lines.extend(["", "必须遵守的术语和风格要求：", glossary.strip()])
    lines.extend(["", "待翻译的英文 SRT：", "", "\n\n".join(source_blocks)])
    return "\n".join(lines).rstrip() + "\n", len(entries), 1


def merge_webchat_translation(
    source_srt: Path,
    response_text: str,
    output_srt: Path,
    target_language: str = "zh-Hans",
    chunk_size: int = 20,
    glossary: str = "",
) -> TranslationResult:
    del glossary
    source = Path(source_srt).expanduser().resolve()
    output = Path(output_srt).expanduser().resolve()
    entries = _speech_entries(source)
    if not entries:
        raise ProcessingError(f"no speech subtitle entries found: {source}")
    translated_entries = parse_srt_text(_extract_srt_response(response_text))
    if translated_entries:
        if len(translated_entries) != len(entries):
            raise ProcessingError(
                f"translated SRT contains {len(translated_entries)} entries, expected {len(entries)}"
            )
        translations: list[str] = []
        for source_entry, translated_entry in zip(entries, translated_entries):
            if translated_entry.index != source_entry.index:
                raise ProcessingError(
                    f"translated SRT changed subtitle index {source_entry.index} to {translated_entry.index}"
                )
            if translated_entry.timecode != source_entry.timecode:
                raise ProcessingError(f"translated SRT changed the timecode for subtitle {source_entry.index}")
            value = translated_entry.text.strip()
            if target_language == "zh-Hans":
                value = to_simplified_chinese(value)
            if not value:
                raise ProcessingError(f"translated SRT subtitle {source_entry.index} is empty")
            translations.append(value)
        write_srt(entries, translations, output)
        return TranslationResult(output_srt=output, entries=len(entries), batches=1)

    batches = list(_chunked(entries, max(1, chunk_size)))
    batch_map = _parse_webchat_response(response_text)
    translations: list[str] = []
    for batch_no, batch in enumerate(batches, start=1):
        items = batch_map.get(batch_no)
        if items is None:
            raise ProcessingError(f"Web Chat response is missing batch {batch_no}")
        if len(items) != len(batch):
            raise ProcessingError(f"batch {batch_no} returned {len(items)} translations, expected {len(batch)}")
        for entry, item in zip(batch, items):
            if isinstance(item, dict):
                item_id = item.get("id")
                if item_id != entry.index:
                    raise ProcessingError(
                        f"batch {batch_no} returned subtitle id {item_id!r}, expected {entry.index}"
                    )
                value = str(item.get("translation", item.get("text", ""))).strip()
            else:
                value = str(item).strip()
            if target_language == "zh-Hans":
                value = to_simplified_chinese(value)
            if not value:
                raise ProcessingError(f"batch {batch_no} contains an empty translation")
            translations.append(value)
    write_srt(entries, translations, output)
    return TranslationResult(output_srt=output, entries=len(entries), batches=len(batches))


def _extract_srt_response(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        raise ProcessingError("paste the translated SRT first")
    fenced = re.findall(r"```(?:srt)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = max(fenced, key=len).strip()
    start = re.search(r"(?m)^\s*1\s*\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->", raw)
    if start:
        raw = raw[start.start():]
    return raw


def _parse_webchat_response(text: str) -> dict[int, list[object]]:
    raw = str(text or "").strip()
    if not raw:
        raise ProcessingError("paste the Web Chat translation response first")
    values: list[object] = []
    try:
        values.append(json.loads(raw))
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        position = 0
        while position < len(raw):
            match = re.search(r"[\[{]", raw[position:])
            if match is None:
                break
            start = position + match.start()
            try:
                value, end = decoder.raw_decode(raw[start:])
            except json.JSONDecodeError:
                position = start + 1
                continue
            values.append(value)
            position = start + end
    if not values:
        raise ProcessingError("Web Chat response does not contain valid JSON")
    parsed = values if len(values) > 1 else values[0]
    if isinstance(parsed, dict) and "batches" in parsed:
        parsed = parsed["batches"]
    if isinstance(parsed, dict):
        parsed = [parsed]
    if isinstance(parsed, list) and parsed and all(isinstance(item, dict) for item in parsed):
        result: dict[int, list[object]] = {}
        for item in parsed:
            batch_no = item.get("batch")
            translations = item.get("translations")
            if not isinstance(batch_no, int) or not isinstance(translations, list):
                raise ProcessingError("each Web Chat batch must contain integer batch and translations array")
            if batch_no in result:
                raise ProcessingError(f"Web Chat response contains duplicate batch {batch_no}")
            result[batch_no] = translations
        return result
    if isinstance(parsed, list):
        return {1: parsed}
    raise ProcessingError("Web Chat response must be a JSON batch array")


def _call_chat(base_url: str, api_key: str, model: str, prompt: str, temperature: float) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": "You are a precise subtitle translator. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ProcessingError(f"LLM request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProcessingError(f"LLM response is not JSON: {exc}") from exc
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProcessingError("LLM response does not match OpenAI-compatible chat completions shape") from exc


def _parse_translation_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProcessingError(f"LLM translation was not valid JSON: {exc}") from exc
