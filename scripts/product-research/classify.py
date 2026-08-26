"""Optional LLM semantic classification.

The MVP is safe by default: if no API key is configured, semantic fields are
marked unavailable instead of being guessed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict
from urllib.request import Request, urlopen

from schemas import SEMANTIC_FIELDS, VIDEO_CATEGORIES, VIDEO_CATEGORY_FIELDS


UNAVAILABLE = "unavailable; needs LLM/manual review"
ALL_LLM_FIELDS = SEMANTIC_FIELDS + VIDEO_CATEGORY_FIELDS


@dataclass
class Classification:
    fields: Dict[str, str]
    provider: str
    model: str
    calls: int
    review_status: str
    error: str = ""


def model_label(provider: str) -> str:
    if provider == "deepseek":
        return os.environ.get("PRODUCT_RESEARCH_LLM_MODEL", "deepseek-v4-flash")
    if provider == "openai":
        return os.environ.get("PRODUCT_RESEARCH_LLM_MODEL", "gpt-4.1-mini")
    return "none"


def unavailable_classification(provider: str = "none", error: str = "") -> Classification:
    return Classification(
        fields={field: UNAVAILABLE for field in ALL_LLM_FIELDS},
        provider=provider,
        model=model_label(provider),
        calls=0,
        review_status="needs_llm_or_manual_review",
        error=error,
    )


def classify_product(name: str, url: str, trimmed_text: str, provider: str, timeout: int = 30) -> Classification:
    if provider == "none":
        return unavailable_classification()
    if provider == "deepseek":
        return classify_with_deepseek(name, url, trimmed_text, timeout=timeout)
    if provider == "openai":
        return classify_with_openai(name, url, trimmed_text, timeout=timeout)
    raise ValueError("unsupported llm provider: %s" % provider)


def build_prompt(name: str, url: str, trimmed_text: str) -> Dict[str, object]:
    return {
        "instruction": (
            "Analyze only the provided webpage excerpt. Do not browse. "
            "If the excerpt does not support a field, return 'unavailable'. "
            "Return concise Chinese field values for an AI SaaS products CSV. "
            "The current research focus is Reference-to-Video / Video-to-Video / 视频二创控制. "
            "First decide whether the product is truly in the AI video domain. "
            "Then decide whether it is directly relevant to Reference-to-Video / Video-to-Video / 视频二创控制. "
            "Non-video products, generic productivity tools, architecture tools, meeting notes, CRM, image-only tools, or audio-only tools should have ai_video_fit=NO."
        ),
        "allowed_video_categories": VIDEO_CATEGORIES,
        "schema": {
            "给谁用": "target users",
            "输入": "what the user inputs",
            "输出": "what the product outputs",
            "解决什么问题": "specific problem solved",
            "为什么值得继续看": "why this product deserves further research",
            "ai_video_fit": "YES, MAYBE, or NO. YES only if the excerpt clearly shows AI video creation/editing/analysis/localization/advertising.",
            "ai_video_evidence": "short evidence from the excerpt; unavailable if not supported",
            "video_category": "1-3 categories from allowed_video_categories, separated by semicolon",
            "reference_to_video_fit": "YES, MAYBE, or NO",
            "reference_to_video_evidence": "short evidence from the excerpt; unavailable if not supported",
        },
        "product": {"name": name, "url": url},
        "webpage_excerpt": trimmed_text[:5000],
    }


def normalize_fields(parsed: Dict[str, object]) -> Dict[str, str]:
    return {field: str(parsed.get(field, "unavailable") or "unavailable") for field in ALL_LLM_FIELDS}


def classify_with_openai(name: str, url: str, trimmed_text: str, timeout: int = 30) -> Classification:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return unavailable_classification("openai", "OPENAI_API_KEY is not set")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = model_label("openai")
    prompt = build_prompt(name, url, trimmed_text)
    body = json.dumps(
        {
            "model": model,
            "input": [
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(prompt, ensure_ascii=False)}]}
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "product_semantic_fields",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ALL_LLM_FIELDS,
                        "properties": {field: {"type": "string"} for field in ALL_LLM_FIELDS},
                    },
                    "strict": True,
                }
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        base_url + "/responses",
        data=body,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        result = unavailable_classification("openai", str(exc))
        result.calls = 1
        return result

    text = payload.get("output_text", "")
    if not text:
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    text += content.get("text", "")
    try:
        parsed = json.loads(text)
    except Exception as exc:
        result = unavailable_classification("openai", "invalid JSON: %s" % exc)
        result.calls = 1
        return result
    return Classification(fields=normalize_fields(parsed), provider="openai", model=model, calls=1, review_status="needs_human_review")


def classify_with_deepseek(name: str, url: str, trimmed_text: str, timeout: int = 30) -> Classification:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return unavailable_classification("deepseek", "DEEPSEEK_API_KEY is not set")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = model_label("deepseek")
    prompt = build_prompt(name, url, trimmed_text)
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict data extraction assistant. Return only valid JSON. Do not browse or infer beyond the supplied excerpt.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "thinking": {"type": "disabled"},
            "stream": False,
            "max_tokens": 1000,
            "temperature": 0,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        base_url + "/chat/completions",
        data=body,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        result = unavailable_classification("deepseek", str(exc))
        result.calls = 1
        return result
    try:
        text = payload["choices"][0]["message"]["content"]
        parsed = parse_json_object(text)
    except Exception as exc:
        result = unavailable_classification("deepseek", "invalid JSON: %s" % exc)
        result.calls = 1
        return result
    return Classification(fields=normalize_fields(parsed), provider="deepseek", model=model, calls=1, review_status="needs_human_review")


def parse_json_object(text: str) -> Dict[str, object]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise
