from __future__ import annotations

import time
from pathlib import Path
from typing import List

import whisper
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from utils import get_env, setup_logger, write_json

logger = setup_logger(__name__)


class WordTimestamp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word: str
    start: float
    end: float


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float
    end: float
    text: str
    words: List[WordTimestamp]


class WhisperStep2Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: List[TranscriptSegment]


def transcribe_with_whisper(video_path: str, model_name: str = "large") -> WhisperStep2Output:
    logger.info(f"Step 2 (Whisper): video={video_path} model={model_name}")
    start_time = time.time()

    model = whisper.load_model(model_name)
    result = model.transcribe(video_path, word_timestamps=True, verbose=False)

    transcript: List[TranscriptSegment] = []
    for seg in result.get("segments", []):
        words: List[WordTimestamp] = []
        for w in seg.get("words", []):
            words.append(
                WordTimestamp(
                    word=str(w.get("word", "")),
                    start=float(w.get("start", 0.0)),
                    end=float(w.get("end", 0.0)),
                )
            )

        transcript.append(
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=str(seg.get("text", "")),
                words=words,
            )
        )

    logger.info(f"Whisper complete: segments={len(transcript)} elapsed={time.time() - start_time:.1f}s")
    return WhisperStep2Output(transcript=transcript)


def main() -> None:
    load_dotenv()

    video_path = get_env("VIDEO_PATH", "videos/orderflow_trading.mp4")
    model_name = get_env("WHISPER_MODEL", "large")

    if not Path(video_path).exists():
        logger.error(f"Video file not found: {video_path}")
        return

    output = transcribe_with_whisper(video_path, model_name=model_name)
    write_json("output/step2_whisper.json", output.model_dump())
    logger.info("Step 2 complete: output/step2_whisper.json")


if __name__ == "__main__":
    main()
