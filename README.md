# Meet-AI-Agent PoC
https://meet-ai-agent-git-main-shaguns-projects-41241d91.vercel.app/
**What this is:** A minimal proof-of-concept repository that ingests a Google Meet recording (mp4),
extracts audio, transcribes (whisper or Google STT), optionally merges diarization, extracts action items
using an LLM prompt, and performs simple assignment matching against a local employee JSON.

**Not production-ready.** This PoC focuses on structure, prompts, and a simple pipeline you can run locally.

## Structure
- `scripts/extract_audio.py` — extracts WAV from MP4 using ffmpeg
- `scripts/transcribe.py` — transcribes audio (supports local Whisper or placeholder for cloud STT)
- `scripts/merge_diarization_transcript.py` — helper to merge diarization results with transcript segments
- `scripts/extract_tasks.py` — calls an LLM (OpenAI) to extract action items into JSON
- `scripts/assign.py` — simple assignment logic using employee profiles
- `app.py` — FastAPI wrapper exposing endpoints for ingest & process
- `requirements.txt` — Python deps (for PoC)
- `Dockerfile` — containerization example

## Quickstart (local)
1. Install ffmpeg (system package).
2. Create a virtualenv and install requirements:
   ```
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Place a sample `meeting.mp4` in the repo root.
4. Run the pipeline:
   ```
   python scripts/extract_audio.py meeting.mp4 audio.wav
   python scripts/transcribe.py audio.wav --model small
   python scripts/extract_tasks.py transcript.json --meeting_date 2025-12-01
   python scripts/assign.py tasks.json employees.json
   ```

## Notes
- `scripts/transcribe.py` supports `whisper` (local) if you install `openai-whisper`.
- `scripts/extract_tasks.py` expects an OpenAI API key in `OPENAI_API_KEY` environment variable and will use the `gpt-4o-mini` or `gpt-4o` family if available. You can modify prompts easily.
- Diarization integration points are marked in comments — recommended libraries: `whisperx` or `pyannote.audio`.

## License
MIT
