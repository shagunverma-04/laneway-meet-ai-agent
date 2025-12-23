#!/bin/bash
# Quick example to run the PoC pipeline locally (assumes ffmpeg installed)
set -e
echo "1) Extract audio"
python scripts/extract_audio.py meeting.mp4 audio.wav || true
echo "2) Transcribe"
python scripts/transcribe.py audio.wav || true
echo "3) Extract tasks"
python scripts/extract_tasks.py transcript.json --meeting_date 2025-12-01 || true
echo "4) Assign"
python scripts/assign.py tasks.json employees.json || true
echo "Done. Check tasks.json and assignments.json"
