from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from utils import get_env, hhmmss_to_seconds, setup_logger

logger = setup_logger(__name__)


_IND = "           "


def _utc_date() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _estimate_duration(timeline: List[Dict[str, Any]]) -> str:
    if not timeline:
        return "Unknown"
    ts = str(timeline[-1].get("timestamp", "00:00:00"))
    try:
        seconds = hhmmss_to_seconds(ts)
    except Exception:
        return "Unknown"
    minutes = seconds / 60
    return f"{minutes:.1f} minutes"


def generate_timeline_section(timeline: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for entry in timeline:
        ts = str(entry.get("timestamp", "00:00:00"))
        trader = str(entry.get("trader", ""))
        visual = str(entry.get("visual", ""))
        pattern = entry.get("pattern")
        context = str(entry.get("context", ""))

        lines.append(f'[{ts}] Trader: "{trader}"')
        lines.append(f"{_IND}Visual: {visual}")
        lines.append(f"{_IND}Pattern: {pattern or ''}")
        lines.append(f"{_IND}Context: {context}")
    return "\n".join(lines) + ("\n" if lines else "")


def generate_rules_section(rules: List[Dict[str, Any]]) -> str:
    if not rules:
        return ""

    lines: List[str] = []
    for r in rules:
        rule_id = int(r.get("rule_id", 0))
        c1 = str(r.get("condition_1", ""))
        c2 = str(r.get("condition_2", ""))
        outcome = str(r.get("outcome", ""))
        prob = float(r.get("probability", 0.0))
        action = str(r.get("action", ""))
        stop_target = str(r.get("stop_target", ""))
        conf = str(r.get("confidence", ""))

        prob_pct = int(round(prob * 100))

        lines.append(f"RULE #{rule_id}: When {c1} AND {c2}")
        lines.append(f"{_IND}→ Outcome: {outcome} ({prob_pct}%)")
        lines.append(f"{_IND}→ Action: {action}")
        lines.append(f"{_IND}→ Stop/Target: {stop_target}")
        lines.append(f"{_IND}→ Confidence: {conf}")

    return "\n".join(lines) + ("\n" if lines else "")


def generate_patterns_section(patterns: List[Dict[str, Any]]) -> str:
    if not patterns:
        return ""

    lines: List[str] = []
    for p in patterns:
        lines.append(f"Pattern: {p.get('name', '')}")
        lines.append(f"  Visual: {p.get('visual', '')}")
        lines.append(f"  Audio: \"{p.get('audio', '')}\"")
        lines.append(f"  Frequency: {p.get('frequency', 0)} times in video")
        lines.append(f"  Success rate: {p.get('success_rate', '')}")
        lines.append(f"  Entry: {p.get('entry', '')}")
        lines.append(f"  Stop: {p.get('stop', '')}")
        lines.append(f"  Target: {p.get('target', '')}")
        lines.append(f"  Timeframe: {p.get('timeframe', '')}")
        lines.append(f"  Prerequisites: {p.get('prerequisites', '')}")
        lines.append(f"  Invalid if: {p.get('invalid_if', '')}")

    return "\n".join(lines) + ("\n" if lines else "")


def generate_confidence_section(confidence_matrix: Dict[str, Any]) -> str:
    scoring = confidence_matrix.get("scoring_rules", {})
    return "\n".join(
        [
            "Scoring Rules:",
            f"- Pattern + Trader confirmation = {scoring.get('pattern_plus_trader_confirmation', 0.95)}",
            f"- Pattern only = {scoring.get('pattern_only', 0.65)}",
            f"- Trader verbal only = {scoring.get('trader_verbal_only', 0.50)}",
            f"- With quantified data (price/volume) = +{scoring.get('with_quantified_data_bonus', 0.15)}",
            f"- Contradicting signals = score * {scoring.get('contradicting_signals_multiplier', 0.5)}",
        ]
    ) + "\n"


def _prioritize_patterns_to_fit(patterns: List[Dict[str, Any]], max_bytes: int, current_prompt_prefix: str) -> List[Dict[str, Any]]:
    def freq(p: Dict[str, Any]) -> int:
        try:
            return int(p.get("frequency", 0))
        except Exception:
            return 0

    ordered = sorted(patterns, key=freq, reverse=True)
    kept: List[Dict[str, Any]] = []

    for p in ordered:
        kept.append(p)
        candidate = current_prompt_prefix + generate_patterns_section(kept)
        if len(candidate.encode("utf-8")) > max_bytes:
            kept.pop()
            break

    return kept


def generate_system_prompt(kg: Dict[str, Any], video_name: str) -> str:
    timeline = list(kg.get("timeline", []))
    rules = list(kg.get("rules", []))
    patterns = list(kg.get("patterns", []))
    confidence_matrix = dict(kg.get("confidence_matrix", {}))

    duration = _estimate_duration(timeline)

    # Decision framework placeholders
    invalid_conditions = " | ".join(
        [str(p.get("invalid_if", "")).strip() for p in patterns if str(p.get("invalid_if", "")).strip()]
    ) or "unknown"

    max_position_size = "unknown"
    required_confirmation = "pattern + trader confirmation"

    # Required confirmations: take top 2 patterns by frequency
    patterns_sorted = sorted(patterns, key=lambda p: int(p.get("frequency", 0) or 0), reverse=True)
    p_x = patterns_sorted[0] if len(patterns_sorted) > 0 else {}
    p_y = patterns_sorted[1] if len(patterns_sorted) > 1 else {}

    visual_signal = str(p_x.get("visual", "")) or "visual signal"
    audio_confirmation = str(p_x.get("audio", "")) or "audio confirmation"

    dom_threshold = "DOM imbalance crosses 0.3 or 0.7"
    price_action = "price breaks significant level"

    header = "\n".join(
        [
            "# ORDERFLOW TRADING SYSTEM PROMPT",
            f"# Knowledge extracted from: {video_name}",
            f"# Duration: {duration}",
            f"# Extraction date: {_utc_date()}",
            "",
        ]
    )

    base_prefix = "\n".join(
        [
            header,
            "## LAYER 1: COMPLETE TIMELINE",
            "",
            generate_timeline_section(timeline),
            "## LAYER 2: DISCOVERED TRADING RULES",
            "",
            generate_rules_section(rules),
            "## LAYER 3: PATTERN SIGNATURE LIBRARY",
            "",
        ]
    )

    # Keep prompt under 50KB: prioritize highest-frequency patterns if needed
    patterns_kept = patterns
    full_patterns_block = generate_patterns_section(patterns_kept)
    candidate = base_prefix + full_patterns_block

    if len(candidate.encode("utf-8")) > 50_000:
        logger.warning("Prompt would exceed 50KB; prioritizing highest-frequency patterns")
        patterns_kept = _prioritize_patterns_to_fit(patterns, 50_000, base_prefix)

    prompt_lines: List[str] = [
        header.rstrip("\n"),
        "## LAYER 1: COMPLETE TIMELINE",
        "",
        generate_timeline_section(timeline).rstrip("\n"),
        "",
        "## LAYER 2: DISCOVERED TRADING RULES",
        "",
        generate_rules_section(rules).rstrip("\n"),
        "",
        "## LAYER 3: PATTERN SIGNATURE LIBRARY",
        "",
        generate_patterns_section(patterns_kept).rstrip("\n"),
        "",
        "## LAYER 4: CONFIDENCE SCORING MATRIX",
        "",
        generate_confidence_section(confidence_matrix).rstrip("\n"),
        "",
        "## DECISION FRAMEWORK",
        "",
        "### Rule Precedence:",
        "1. If Pattern + Trader confirmation → confidence 0.95 → Execute",
        "2. If Pattern alone → confidence 0.65 → Wait for confirmation",
        "3. If contradicting signals → Halt execution",
        "",
        "### Prohibited Actions:",
        f"- NEVER enter when {invalid_conditions}",
        f"- NEVER exceed {max_position_size}",
        f"- ALWAYS wait for {required_confirmation}",
        "",
        "### Required Confirmations:",
        f"- For Pattern {p_x.get('name', 'X')}: Requires {visual_signal} + {audio_confirmation}",
        f"- For Pattern {p_y.get('name', 'Y')}: Requires {dom_threshold} + {price_action}",
        "",
    ]

    prompt = "\n".join(prompt_lines).strip() + "\n"

    if len(prompt.encode("utf-8")) > 50_000:
        logger.warning("Prompt still exceeds 50KB after pattern prioritization")

    return prompt


def main() -> None:
    load_dotenv()

    kg_path = Path(get_env("KG_JSON", "output/step4_knowledge_graph.json"))
    if not kg_path.exists():
        logger.error(f"Knowledge graph not found: {kg_path}")
        return

    kg = json.loads(kg_path.read_text(encoding="utf-8"))
    video_name = Path(get_env("VIDEO_PATH", "videos/orderflow_trading.mp4")).name

    prompt = generate_system_prompt(kg, video_name=video_name)

    out_path = Path("output/system_prompt.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(prompt, encoding="utf-8")

    logger.info(f"Step 5 complete: {out_path}")
    logger.info(f"Prompt size: {len(prompt.encode('utf-8'))} bytes")


if __name__ == "__main__":
    main()
