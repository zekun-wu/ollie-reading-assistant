"""
Shared LLM prompt logger for eye-tracking and manual assistance.
Redacts base64 image data, logs the prompt, and optionally saves to JSON.
"""
import copy
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _redact_payload(payload: dict) -> dict:
    """Deep copy payload and replace image_url base64 data with a placeholder."""
    redacted = copy.deepcopy(payload)
    messages = redacted.get("messages") or []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for i, part in enumerate(content):
            if not isinstance(part, dict):
                continue
            if part.get("type") != "image_url":
                continue
            image_url = part.get("image_url") or {}
            url = image_url.get("url") or ""
            if isinstance(url, str) and url.startswith("data:image/") and ";base64," in url:
                detail = image_url.get("detail", "high")
                content[i] = {
                    "type": "image_url",
                    "image_url": {"url": "<image_redacted>", "detail": detail},
                }
    return redacted


def emit_llm_prompt(payload: dict, label: str) -> None:
    """
    Log the LLM prompt (with images redacted) and optionally save to JSON.
    Call before requests.post in eye_tracking_llm_service and chatgpt_service.
    """
    redacted = _redact_payload(payload)
    try:
        payload_str = json.dumps(redacted, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        payload_str = str(redacted)
    logger.info("LLM prompt [%s]: %s", label, payload_str)

    if os.environ.get("SAVE_LLM_PROMPTS") == "1":
        backend_dir = Path(__file__).resolve().parent.parent.parent
        log_dir = backend_dir / "prompt_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = label.replace(" ", "_")
        path = log_dir / f"llm_prompt_{timestamp}_{safe_label}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(redacted, f, indent=2, ensure_ascii=False)
            logger.debug("Saved LLM prompt to %s", path)
        except OSError as e:
            logger.warning("Failed to save LLM prompt to %s: %s", path, e)
