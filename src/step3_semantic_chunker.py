from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from utils import get_env, hhmmss_to_seconds, setup_logger, write_json

logger = setup_logger(__name__)


class GeminiOrderflowState(BaseModel):
    model_config = ConfigDict(extra="allow")

    dom_imbalance: float
    bid_ask_ratio: float
    aggressor_side: str
    price_level: float


class GeminiTimelineItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: str
    frame_description: str
    orderflow_state: Optional[GeminiOrderflowState] = None
    pattern_detected: Optional[str] = None


class WhisperTranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="allow")

    start: float
    end: float
    text: str


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: int
    start_time: str
    end_time: str
    trigger: str
    visual_events: List[Dict[str, Any]]
    audio_events: List[Dict[str, Any]]
    pattern: Optional[str] = None


class SemanticChunkerStep3Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: List[Segment]


def _clip_text_embeddings(texts: List[str]) -> np.ndarray:
    import open_clip

    device = "cpu"
    model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    model = model.to(device)
    tokenizer = open_clip.get_tokenizer("ViT-B-32")

    with torch.no_grad():
        tokens = tokenizer(texts)
        tokens = tokens.to(device)
        emb = model.encode_text(tokens)
        emb = emb / emb.norm(dim=-1, keepdim=True)

    return emb.cpu().numpy()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _audio_segments_by_second(transcript: List[WhisperTranscriptSegment]) -> Dict[int, List[WhisperTranscriptSegment]]:
    by_second: Dict[int, List[WhisperTranscriptSegment]] = {}
    for seg in transcript:
        start = int(seg.start)
        end = int(seg.end)
        for s in range(start, end + 1):
            by_second.setdefault(s, []).append(seg)
    return by_second


def _contains_emphasis(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ["this is", "watch", "key level", "important", "critical", "right here"])


def _extract_price_mentions(text: str) -> List[float]:
    nums = re.findall(r"\b\d{3,5}(?:\.\d+)?\b", text)
    out: List[float] = []
    for n in nums:
        try:
            out.append(float(n))
        except Exception:
            continue
    return out


def _detect_volume_surge(description: str) -> bool:
    d = description.lower()
    if "volume" not in d:
        return False
    return any(k in d for k in ["surge", "spike", "explosion", "2x", "two times"])


def _detect_price_break(event: GeminiTimelineItem, prev: GeminiTimelineItem | None, significant_levels: List[float]) -> bool:
    if not event.orderflow_state or not prev or not prev.orderflow_state:
        return False

    p = event.orderflow_state.price_level
    p_prev = prev.orderflow_state.price_level

    for lvl in significant_levels:
        if (p_prev < lvl <= p) or (p_prev > lvl >= p):
            return True

    if event.pattern_detected and any(k in event.pattern_detected.lower() for k in ["break", "breakout", "breakdown"]):
        return True

    return False


def _detect_dom_imbalance_shift(event: GeminiTimelineItem, prev: GeminiTimelineItem | None) -> bool:
    if not event.orderflow_state:
        return False

    curr = float(event.orderflow_state.dom_imbalance)
    prev_val = float(prev.orderflow_state.dom_imbalance) if prev and prev.orderflow_state else None

    if prev_val is None:
        return curr < 0.3 or curr > 0.7

    was_extreme = prev_val < 0.3 or prev_val > 0.7
    is_extreme = curr < 0.3 or curr > 0.7
    return (not was_extreme) and is_extreme


def _build_segments(
    timeline: List[GeminiTimelineItem],
    transcript: List[WhisperTranscriptSegment],
    boundaries: List[Tuple[int, str]],
) -> List[Segment]:
    audio_by_second = _audio_segments_by_second(transcript)

    segments: List[Segment] = []
    for idx, (start_i, trigger) in enumerate(boundaries):
        end_i = (boundaries[idx + 1][0] - 1) if idx + 1 < len(boundaries) else len(timeline) - 1
        if end_i < start_i:
            continue

        start_ts = timeline[start_i].timestamp
        end_ts = timeline[end_i].timestamp

        visual_events = [t.model_dump() for t in timeline[start_i : end_i + 1]]

        start_sec = hhmmss_to_seconds(start_ts)
        end_sec = hhmmss_to_seconds(end_ts)

        audio_events: List[Dict[str, Any]] = []
        seen = set()
        for sec in range(start_sec, end_sec + 1):
            for seg in audio_by_second.get(sec, []):
                key = (seg.start, seg.end, seg.text)
                if key in seen:
                    continue
                seen.add(key)
                audio_events.append(seg.model_dump())

        patterns = [t.pattern_detected for t in timeline[start_i : end_i + 1] if t.pattern_detected]
        pattern = Counter(patterns).most_common(1)[0][0] if patterns else None

        segments.append(
            Segment(
                segment_id=idx + 1,
                start_time=start_ts,
                end_time=end_ts,
                trigger=trigger,
                visual_events=visual_events,
                audio_events=audio_events,
                pattern=pattern,
            )
        )

    return segments


def _uniform_fallback(timeline: List[GeminiTimelineItem], transcript: List[WhisperTranscriptSegment], chunk_size: int = 60) -> List[Segment]:
    if not timeline:
        return []

    boundaries: List[Tuple[int, str]] = []
    start_sec = hhmmss_to_seconds(timeline[0].timestamp)
    for i, ev in enumerate(timeline):
        sec = hhmmss_to_seconds(ev.timestamp)
        if sec - start_sec >= chunk_size:
            boundaries.append((i, "UNIFORM_FALLBACK"))
            start_sec = sec

    if not boundaries or boundaries[0][0] != 0:
        boundaries.insert(0, (0, "UNIFORM_FALLBACK"))

    return _build_segments(timeline, transcript, boundaries)


def create_semantic_chunks(gemini_json: Dict[str, Any], whisper_json: Dict[str, Any]) -> SemanticChunkerStep3Output:
    logger.info("Step 3 (Semantic Chunker): starting")

    timeline = [GeminiTimelineItem.model_validate(x) for x in gemini_json.get("timeline", [])]
    transcript = [WhisperTranscriptSegment.model_validate(x) for x in whisper_json.get("transcript", [])]

    if not timeline:
        return SemanticChunkerStep3Output(segments=[])

    # Build list of significant levels mentioned by trader
    significant_levels: List[float] = []
    for seg in transcript:
        significant_levels.extend(_extract_price_mentions(seg.text))

    # CLIP-based segmentation (text embeddings over Gemini frame descriptions)
    descriptions = [t.frame_description for t in timeline]
    clip_threshold = float(get_env("CLIP_SIMILARITY_THRESHOLD", "0.85"))

    similarities: List[float] = []
    try:
        if len(descriptions) >= 2:
            embeddings = _clip_text_embeddings(descriptions)
            for i in range(1, len(embeddings)):
                similarities.append(_cosine_similarity(embeddings[i - 1], embeddings[i]))
        logger.info("CLIP text embedding similarity computed")
    except Exception as e:
        logger.error(f"CLIP embedding failed (will proceed without CLIP boundaries): {e}")
        similarities = [1.0] * max(0, len(descriptions) - 1)

    audio_by_second = _audio_segments_by_second(transcript)

    boundaries: List[Tuple[int, str]] = [(0, "START")]

    for i in range(1, len(timeline)):
        ev = timeline[i]
        prev = timeline[i - 1]
        sec = hhmmss_to_seconds(ev.timestamp)

        trigger: Optional[str] = None

        if _detect_dom_imbalance_shift(ev, prev):
            trigger = "DOM_IMBALANCE_SHIFT"
        elif _detect_price_break(ev, prev, significant_levels):
            trigger = "PRICE_LEVEL_BREAK"
        elif _detect_volume_surge(ev.frame_description):
            trigger = "VOLUME_SURGE"
        else:
            for seg in audio_by_second.get(sec, []):
                if _contains_emphasis(seg.text):
                    trigger = "TRADER_EMPHASIS"
                    break

        if trigger is None and similarities:
            sim = similarities[i - 1]
            if sim < clip_threshold:
                trigger = "CLIP_BOUNDARY"

        if trigger:
            boundaries.append((i, trigger))

    # If we found no meaningful boundaries besides the start, fallback to uniform chunks
    if len(boundaries) <= 1:
        logger.warning("No semantic boundaries found, falling back to 60-second uniform chunks")
        segments = _uniform_fallback(timeline, transcript, chunk_size=60)
        return SemanticChunkerStep3Output(segments=segments)

    segments = _build_segments(timeline, transcript, boundaries)
    return SemanticChunkerStep3Output(segments=segments)


def main() -> None:
    load_dotenv()

    gemini_path = Path(get_env("GEMINI_JSON", "output/step1_gemini.json"))
    whisper_path = Path(get_env("WHISPER_JSON", "output/step2_whisper.json"))

    if not gemini_path.exists():
        logger.error(f"Gemini JSON not found: {gemini_path}")
        return
    if not whisper_path.exists():
        logger.error(f"Whisper JSON not found: {whisper_path}")
        return

    gemini_json = json.loads(gemini_path.read_text(encoding="utf-8"))
    whisper_json = json.loads(whisper_path.read_text(encoding="utf-8"))

    output = create_semantic_chunks(gemini_json, whisper_json)
    write_json("output/step3_semantic_chunks.json", output.model_dump())
    logger.info("Step 3 complete: output/step3_semantic_chunks.json")


if __name__ == "__main__":
    main()
