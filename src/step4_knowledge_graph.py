from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from utils import get_env, hhmmss_to_seconds, setup_logger, write_json

logger = setup_logger(__name__)


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    trader: str
    visual: str
    pattern: Optional[str] = None
    context: str


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: int
    condition_1: str
    condition_2: str
    outcome: str
    probability: float
    action: str
    stop_target: str
    confidence: str


class PatternSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    visual: str
    audio: str
    frequency: int
    success_rate: str
    entry: str
    stop: str
    target: str
    timeframe: str
    prerequisites: str
    invalid_if: str


class KnowledgeGraphStep4Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline: List[TimelineEntry]
    rules: List[Rule]
    patterns: List[PatternSignature]
    confidence_matrix: Dict[str, Any]


def _audio_by_second(transcript: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    by_second: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for seg in transcript:
        start = int(seg.get("start", 0))
        end = int(seg.get("end", 0))
        for s in range(start, end + 1):
            by_second[s].append(seg)
    return by_second


def _format_visual(frame_description: str, orderflow_state: Optional[Dict[str, Any]]) -> str:
    if not orderflow_state:
        return frame_description

    parts = []
    for key in ["dom_imbalance", "bid_ask_ratio", "aggressor_side", "price_level"]:
        if key in orderflow_state and orderflow_state[key] is not None:
            parts.append(f"{key}={orderflow_state[key]}")

    if not parts:
        return frame_description

    return f"Orderflow({', '.join(parts)}); {frame_description}"


def _keywords_present(text: str, keywords: List[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _segment_outcome(audio_text: str) -> str:
    positive = ["profit", "winner", "nice", "good trade", "paid", "target hit", "took profit", "in the money"]
    negative = ["stopped", "stop out", "loss", "loser", "scratch", "breakeven", "wrong"]

    pos = _keywords_present(audio_text, positive)
    neg = _keywords_present(audio_text, negative)

    if pos and not neg:
        return "profitable"
    if neg and not pos:
        return "stopped_out"
    if pos and neg:
        return "mixed"
    return "unknown"


def _extract_stop_target(text: str) -> Tuple[str, str]:
    t = text.lower()

    stop_match = re.search(r"stop(?:\s+(?:is|at))?\s+(\d{2,6}(?:\.\d+)?)", t)
    target_match = re.search(r"target(?:\s+(?:is|at))?\s+(\d{2,6}(?:\.\d+)?)", t)

    stop = stop_match.group(1) if stop_match else ""
    target = target_match.group(1) if target_match else ""
    return stop, target


def _extract_rule_conditions(text: str) -> Tuple[str, str]:
    t = text.strip()
    lower = t.lower()

    anchor = None
    if "when " in lower:
        anchor = lower.find("when ")
        clause = t[anchor + 5 :]
    elif lower.startswith("if ") or " if " in lower:
        anchor = lower.find("if ")
        clause = t[anchor + 3 :]
    else:
        return "", ""

    clause = clause.strip()

    if " and " in clause.lower():
        parts = re.split(r"\band\b", clause, maxsplit=1, flags=re.IGNORECASE)
        c1 = parts[0].strip(" ,.")
        c2 = parts[1].strip(" ,.")
        return c1, c2

    return clause.strip(" ,."), "TRUE"


def _extract_action(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ["go long", "buy", "enter long", "long here"]):
        return "enter_long"
    if any(k in lower for k in ["go short", "sell", "enter short", "short here"]):
        return "enter_short"
    if any(k in lower for k in ["take profit", "took profit", "target"]):
        return "take_profit"
    if any(k in lower for k in ["stop", "stopped"]):
        return "stop_out"
    return "trader_action_stated"


def assemble_knowledge_graph(
    gemini_json: Dict[str, Any],
    whisper_json: Dict[str, Any],
    segments_json: Dict[str, Any],
) -> KnowledgeGraphStep4Output:
    logger.info("Step 4 (Knowledge Graph): starting")

    timeline_in = gemini_json.get("timeline", [])
    transcript = whisper_json.get("transcript", [])
    segments = segments_json.get("segments", [])

    audio_by_second = _audio_by_second(transcript)

    timeline: List[TimelineEntry] = []
    prev_visual = ""

    for ev in timeline_in:
        ts = str(ev.get("timestamp", "00:00:00"))
        sec = hhmmss_to_seconds(ts)

        trader_quotes = [str(a.get("text", "")).strip() for a in audio_by_second.get(sec, []) if str(a.get("text", "")).strip()]
        trader = " ".join(trader_quotes)

        visual = _format_visual(str(ev.get("frame_description", "")), ev.get("orderflow_state"))
        pattern = ev.get("pattern_detected")
        context = prev_visual

        timeline.append(
            TimelineEntry(
                timestamp=ts,
                trader=trader,
                visual=visual,
                pattern=pattern,
                context=context,
            )
        )

        prev_visual = visual

    # Pattern extraction from semantic segments
    pattern_occurrences: List[str] = [s.get("pattern") for s in segments if s.get("pattern")]
    pattern_counts: Counter[str] = Counter(pattern_occurrences)

    # Success/failure heuristic from audio in each segment
    success_counts: Counter[str] = Counter()
    total_counts: Counter[str] = Counter()

    for seg in segments:
        pat = seg.get("pattern")
        if not pat:
            continue
        total_counts[pat] += 1
        audio_text = " ".join([str(a.get("text", "")) for a in seg.get("audio_events", [])])
        if _segment_outcome(audio_text) == "profitable":
            success_counts[pat] += 1

    patterns: List[PatternSignature] = []

    for pat, freq in pattern_counts.most_common():
        success = int(success_counts.get(pat, 0))
        total = int(total_counts.get(pat, freq))
        pct = int(round((success / total) * 100)) if total else 0

        # Representative visual and audio
        rep_visual = ""
        rep_audio = ""
        durations: List[int] = []

        for seg in segments:
            if seg.get("pattern") != pat:
                continue

            try:
                start_sec = hhmmss_to_seconds(seg.get("start_time", "00:00:00"))
                end_sec = hhmmss_to_seconds(seg.get("end_time", "00:00:00"))
                durations.append(max(0, end_sec - start_sec))
            except Exception:
                pass

            if not rep_visual:
                ve = seg.get("visual_events", [])
                if ve:
                    rep_visual = str(ve[0].get("frame_description", ""))

            if not rep_audio:
                ae = seg.get("audio_events", [])
                if ae:
                    rep_audio = str(ae[0].get("text", ""))

        avg_dur = int(round(sum(durations) / len(durations))) if durations else 0
        timeframe = f"≈{avg_dur}s" if avg_dur else "Unknown"

        # Extract stop/target from representative audio
        stop_val, target_val = _extract_stop_target(rep_audio)

        patterns.append(
            PatternSignature(
                name=str(pat),
                visual=rep_visual or "",
                audio=rep_audio or "",
                frequency=int(freq),
                success_rate=f"{success}/{total} ({pct}%)",
                entry="Trigger condition derived from segment boundary and orderflow cues",
                stop=f"{stop_val}" if stop_val else "Unknown",
                target=f"{target_val}" if target_val else "Unknown",
                timeframe=timeframe,
                prerequisites="DOM/price/volume conditions observed in segment",
                invalid_if="Contradicting signals or trader disqualifies setup",
            )
        )

    if len(patterns) < 3:
        logger.warning("Pattern extraction returned <3 patterns; video may be low-information")

    # Rule extraction from trader speech
    rules: List[Rule] = []
    rule_statements: List[str] = []

    for seg in transcript:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        lower = text.lower()
        if "when" in lower or " if " in lower or lower.startswith("if "):
            c1, c2 = _extract_rule_conditions(text)
            if not c1:
                continue
            rule_statements.append(text)

    statement_counts = Counter([s.lower().strip() for s in rule_statements])
    total_rule_mentions = sum(statement_counts.values())

    rule_id = 0
    for statement_norm, occ in statement_counts.most_common():
        rule_id += 1
        original = next((s for s in rule_statements if s.lower().strip() == statement_norm), statement_norm)
        c1, c2 = _extract_rule_conditions(original)
        action = _extract_action(original)
        stop_val, target_val = _extract_stop_target(original)

        stop_target = ""
        if stop_val or target_val:
            stop_target = f"stop={stop_val} target={target_val}".strip()

        # Link rule to pattern if mentioned
        mentioned_pattern = None
        for p in patterns:
            if p.name.lower() in original.lower():
                mentioned_pattern = p.name
                break

        prob = 0.0
        outcome = "Observed outcome"
        if mentioned_pattern and total_counts.get(mentioned_pattern, 0) > 0:
            success = int(success_counts.get(mentioned_pattern, 0))
            total = int(total_counts.get(mentioned_pattern, 0))
            prob = success / total if total else 0.0
            outcome = "profitable" if prob >= 0.5 else "mixed"

        rules.append(
            Rule(
                rule_id=rule_id,
                condition_1=c1,
                condition_2=c2,
                outcome=outcome,
                probability=float(prob),
                action=action,
                stop_target=stop_target or "Unknown",
                confidence=f"{occ}/{total_rule_mentions}" if total_rule_mentions else f"{occ}/{occ}",
            )
        )

    confidence_matrix = {
        "scoring_rules": {
            "pattern_plus_trader_confirmation": 0.95,
            "pattern_only": 0.65,
            "trader_verbal_only": 0.50,
            "with_quantified_data_bonus": 0.15,
            "contradicting_signals_multiplier": 0.5,
        }
    }

    return KnowledgeGraphStep4Output(
        timeline=timeline,
        rules=rules,
        patterns=patterns,
        confidence_matrix=confidence_matrix,
    )


def main() -> None:
    load_dotenv()

    gemini_path = Path(get_env("GEMINI_JSON", "output/step1_gemini.json"))
    whisper_path = Path(get_env("WHISPER_JSON", "output/step2_whisper.json"))
    segments_path = Path(get_env("SEGMENTS_JSON", "output/step3_semantic_chunks.json"))

    for p in [gemini_path, whisper_path, segments_path]:
        if not p.exists():
            logger.error(f"Required input not found: {p}")
            return

    gemini_json = json.loads(gemini_path.read_text(encoding="utf-8"))
    whisper_json = json.loads(whisper_path.read_text(encoding="utf-8"))
    segments_json = json.loads(segments_path.read_text(encoding="utf-8"))

    kg = assemble_knowledge_graph(gemini_json, whisper_json, segments_json)
    write_json("output/step4_knowledge_graph.json", kg.model_dump())
    logger.info("Step 4 complete: output/step4_knowledge_graph.json")


if __name__ == "__main__":
    main()
