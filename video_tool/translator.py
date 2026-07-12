from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .chinese import to_simplified_chinese
from .processor import ProcessingError
from .srt import SrtEntry, parse_srt, write_srt


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
