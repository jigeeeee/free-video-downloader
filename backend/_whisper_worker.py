"""Whisper worker — runs in a subprocess. Outputs JSON to stdout."""

import argparse
import json
import os
import sys

# Fix: our project has a module named "queue" that shadows Python's stdlib.
# Ensure the project root (not backend/) is on sys.path first so that when
# third-party libs "import queue" they find the stdlib, not our backend/queue.py.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
# Pop backend/ from sys.path[0] so it doesn't shadow stdlib
if os.path.abspath(sys.path[0]) == os.path.abspath(_THIS_DIR):
    sys.path.pop(0)
sys.path.insert(0, _PROJECT_ROOT)

os.environ["TQDM_DISABLE"] = "1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--model", default="base")
    parser.add_argument("--language", default=None)
    args = parser.parse_args()

    import whisper
    model = whisper.load_model(args.model)
    opts = {"fp16": False, "verbose": False}
    if args.language:
        opts["language"] = args.language

    # Redirect whisper's stdout chatter away from our JSON output
    old_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        result = model.transcribe(args.file, **opts)
    finally:
        sys.stdout = old_stdout

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start": round(seg.get("start", 0), 2),
            "end": round(seg.get("end", 0), 2),
            "text": seg.get("text", "").strip(),
        })

    output = {
        "text": result.get("text", "").strip(),
        "text_preview": result.get("text", "")[:500],
        "segments": segments,
        "language": result.get("language", "unknown"),
        "duration": round(result.get("duration", 0), 1),
        "model": args.model,
    }
    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
