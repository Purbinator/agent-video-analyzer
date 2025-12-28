# Agent Video Analyzer - Orderflow Video Analysis Agent

This repository implements a production-ready video analyzer that extracts orderflow trading knowledge from videos with near-zero information loss.

## Core Objective

Build a system that processes trading videos through a **3-channel pipeline** and generates a hierarchical, LLM-ready **system prompt** containing all extracted knowledge.

**Architecture:** Video Input → [3 Parallel Channels] → Knowledge Graph → System Prompt

- **Channel 1: Gemini 1.5 Pro** (Dense multimodal understanding)
- **Channel 2: Whisper** (Precision transcription with word-level timestamps)
- **Channel 3: Semantic Chunker** (Event-driven segmentation)

The pipeline produces `output/system_prompt.txt` with the exact 4-layer hierarchy required.

## System Requirements

- **Ubuntu**: 24.04
- **Python**: 3.8+ with pip
- **Memory**: 8GB+ recommended (for Whisper large model)
- **Storage**: 10GB+ for models and video processing
- **API Keys**: Google Gemini API key required

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd agent-video-analyzer

# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Prepare Video

Place your orderflow trading video in the `videos/` directory:
```bash
cp /path/to/your/video.mp4 videos/orderflow_trading.mp4
```

### 3. Run the Pipeline

```bash
# Run individual steps in sequence
cd src
python3 step1_gemini.py
python3 step2_whisper.py
python3 step3_semantic_chunker.py
python3 step4_knowledge_graph.py
python3 step5_prompt_generator.py
```

## Pipeline Steps

### Step 1: Gemini Video Processing
```bash
python3 src/step1_gemini.py
```
- Processes video at 1 FPS with Gemini 1.5 Pro
- Extracts frame-by-frame visual analysis with timestamps
- Captures orderflow patterns, DOM imbalances, price action
- Output: `output/step1_gemini.json`

### Step 2: Whisper Transcription
```bash
python3 src/step2_whisper.py
```
- Transcribes audio with Whisper large model
- Word-level timestamps with millisecond precision
- Captures trader intent, emphasis, tone
- Output: `output/step2_whisper.json`

### Step 3: Semantic Chunking
```bash
python3 src/step3_semantic_chunker.py
```
- Event-driven segmentation (no uniform sampling)
- Identifies logical boundaries from DOM changes, price breaks, trader emphasis
- Output: `output/step3_semantic_chunks.json`

### Step 4: Knowledge Graph Assembly
```bash
python3 src/step4_knowledge_graph.py
```
- Merges timeline events with timestamps
- Extracts trading rules and pattern signatures
- Builds confidence scoring matrix
- Output: `output/step4_knowledge_graph.json`

### Step 5: System Prompt Generation
```bash
python3 src/step5_prompt_generator.py
```
- Generates hierarchical system prompt
- 4-layer structure: Timeline → Rules → Patterns → Confidence Matrix
- Output: `output/system_prompt.txt` (FINAL OUTPUT)

## Project Structure

```
orderflow-analyzer/
├── src/
│   ├── __init__.py
│   ├── utils.py                  # Shared utilities
│   ├── step1_gemini.py           # Gemini video processor
│   ├── step2_whisper.py          # Whisper transcription
│   ├── step3_semantic_chunker.py # Semantic segmentation
│   ├── step4_knowledge_graph.py  # Knowledge graph assembly
│   └── step5_prompt_generator.py # System prompt generation
├── output/
│   ├── step1_gemini.json         # Gemini output
│   ├── step2_whisper.json        # Whisper output
│   ├── step3_semantic_chunks.json # Semantic chunks
│   ├── step4_knowledge_graph.json # Knowledge graph
│   └── system_prompt.txt         # FINAL OUTPUT
├── videos/
│   └── orderflow_trading.mp4     # Your video here
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
└── README.md                     # This file
```

## Output Structure

The final `output/system_prompt.txt` contains:

### Layer 1: COMPLETE TIMELINE
```
[HH:MM:SS] Trader: "<exact quote>"
           Visual: <DOM state, price action, chart pattern>
           Pattern: <identified setup>
           Context: <what preceded this moment>
```

### Layer 2: DISCOVERED RULES
```
RULE #N: When <condition_1> AND <condition_2>
         → Outcome: <observed result with probability %>
         → Action: <trader's response>
         → Stop/Target: <risk parameters>
         → Confidence: <pattern count>/<total>
```

### Layer 3: PATTERN SIGNATURES
```
Pattern: <name>
  Visual: <what appears on screen>
  Audio: "<trader confirmation quote>"
  Frequency: X times in video
  Success rate: X/X (%)
  Entry/Stop/Target: <explicit rules>
  Prerequisites/Invalid conditions
```

### Layer 4: CONFIDENCE MATRIX
```
- Pattern + Trader confirmation = 0.95
- Pattern only = 0.65
- Trader verbal only = 0.50
- With quantified data = +0.15
- Contradicting signals = score * 0.5
```

## Configuration

Edit `.env` file:
```bash
# Google Gemini API Key (required)
GEMINI_API_KEY=your_key_here

# Video file path
VIDEO_PATH=videos/orderflow_trading.mp4

# Processing settings
GEMINI_FPS=1           # Frame sampling rate
WHISPER_MODEL=large    # Whisper model size
MAX_RETRIES=3          # API retry attempts
```

## Performance Targets

- **60-minute video** → 15 minutes total processing
- **Final prompt size**: 20-40KB
- **Pattern extraction accuracy**: >90%
- **Information loss**: <2%

## Error Handling

- Gemini API failures: Auto-retry with exponential backoff
- Whisper failures: Logged, pipeline continues with Gemini audio
- No semantic boundaries: Falls back to 60-second uniform chunks
- Low pattern extraction: Video flagged as low-information

## Troubleshooting

### Issue: "Video file not found"
**Solution:** Ensure video is in `videos/` directory and path is correct in `.env`

### Issue: "GEMINI_API_KEY not set"
**Solution:** Add your API key to `.env` file

### Issue: Whisper model download fails
**Solution:** Check internet connection, ensure sufficient disk space

### Issue: Out of memory during processing
**Solution:** Use smaller Whisper model (`WHISPER_MODEL=base`) or process shorter videos

## Development

### Run individual steps
```bash
cd src
python3 step1_gemini.py
python3 step2_whisper.py
python3 step3_semantic_chunker.py
python3 step4_knowledge_graph.py
python3 step5_prompt_generator.py
```

### Inspect intermediate outputs
```bash
cat output/step1_gemini.json | jq
cat output/step4_knowledge_graph.json | jq
cat output/system_prompt.txt
```

## Task Runner VM Setup

The repository also includes VM setup scripts for cto.new task runner:

```bash
npm run setup   # Configure VM
npm run verify  # Verify configuration
npm test        # Run tests
```

## License

MIT
