from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from utils import get_env, setup_logger, write_json

logger = setup_logger(__name__)


class OrderflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dom_imbalance: float = Field(description="DOM imbalance ratio")
    bid_ask_ratio: float = Field(description="Bid/Ask ratio")
    aggressor_side: str = Field(description="buy or sell")
    price_level: float = Field(description="Current price level")


class TimelineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(description="HH:MM:SS")
    frame_description: str
    orderflow_state: Optional[OrderflowState] = None
    pattern_detected: Optional[str] = None


class TraderSpeechItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(description="HH:MM:SS")
    text: str
    confidence: str = Field(description="high/medium/low")


class VisualAudioAlignmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_event: str
    audio_confirmation: str
    timestamp: str = Field(description="HH:MM:SS")


class GeminiStep1Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline: List[TimelineItem]
    trader_speech: List[TraderSpeechItem]
    visual_audio_alignment: List[VisualAudioAlignmentItem]


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response did not contain valid JSON object")
    return text[start : end + 1]


def process_video_with_gemini(video_path: str, api_key: str, fps: int = 1, max_retries: int = 3) -> GeminiStep1Output:
    logger.info(f"Step 1 (Gemini): video={video_path} fps={fps}")

    genai.configure(api_key=api_key)

    logger.info("Uploading video to Gemini...")
    video_file = genai.upload_file(path=video_path)

    while video_file.state.name == "PROCESSING":
        logger.info("Gemini is processing uploaded video...")
        time.sleep(5)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError("Gemini failed to process uploaded video")

    prompt = f"""
You are an expert orderflow trading analyst.

Analyze this trading video frame-by-frame at {fps} FPS.

Return STRICT JSON ONLY (no markdown, no commentary) with this exact schema:

{{
  "timeline": [
    {{
      "timestamp": "HH:MM:SS",
      "frame_description": "...",
      "orderflow_state": {{
        "dom_imbalance": 0.45,
        "bid_ask_ratio": 0.45,
        "aggressor_side": "sell",
        "price_level": 4850.50
      }},
      "pattern_detected": "rejection_at_resistance"
    }}
  ],
  "trader_speech": [
    {{"timestamp": "HH:MM:SS", "text": "...", "confidence": "high"}}
  ],
  "visual_audio_alignment": [
    {{"visual_event": "...", "audio_confirmation": "...", "timestamp": "HH:MM:SS"}}
  ]
}}

CRITICAL INSTRUCTIONS:
- Include an entry in timeline for EVERY SECOND of the video (HH:MM:SS).
- Never summarize or compress: preserve all visible details.
- Preserve exact timestamps to second precision.
- Preserve trader quotes verbatim in trader_speech.
- If an orderflow metric is not visible at a timestamp, set orderflow_state to null.
- If no pattern is detected, set pattern_detected to null.
""".strip()

    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    )

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Requesting analysis from Gemini (attempt {attempt}/{max_retries})...")
            response = model.generate_content([video_file, prompt], request_options={"timeout": 3600})

            raw = response.text or ""
            Path("output").mkdir(parents=True, exist_ok=True)
            Path("output/step1_gemini.raw.txt").write_text(raw, encoding="utf-8")

            json_str = raw
            try:
                data = json.loads(json_str)
            except Exception:
                data = json.loads(_extract_json(raw))

            parsed = GeminiStep1Output.model_validate(data)
            return parsed

        except Exception as e:
            logger.error(f"Gemini request failed: {e}")
            if attempt == max_retries:
                raise
            backoff = 2 ** (attempt - 1)
            logger.info(f"Retrying in {backoff}s...")
            time.sleep(backoff)

    raise RuntimeError("Unreachable")


def main() -> None:
    load_dotenv()

    video_path = get_env("VIDEO_PATH", "videos/orderflow_trading.mp4")
    api_key = get_env("GEMINI_API_KEY")
    fps = int(get_env("GEMINI_FPS", "1"))
    max_retries = int(get_env("MAX_RETRIES", "3"))

    if not Path(video_path).exists():
        logger.error(f"Video file not found: {video_path}")
        return

    output = process_video_with_gemini(video_path, api_key, fps=fps, max_retries=max_retries)
    write_json("output/step1_gemini.json", output.model_dump())
    logger.info("Step 1 complete: output/step1_gemini.json")


if __name__ == "__main__":
    main()
