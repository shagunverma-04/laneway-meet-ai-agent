# Employee Name Recognition - Implementation Guide

## Overview
Implemented a two-layer approach to improve employee name recognition in meeting transcripts:

1. **During Transcription** (Whisper hints)
2. **During Task Extraction** (LLM correction)

## How It Works

### Layer 1: Transcription Hints
When transcribing audio, Whisper now receives employee names as "prompt hints":
- **OpenAI Whisper API**: Uses the `prompt` parameter
- **Local Whisper**: Uses the `initial_prompt` parameter

Example prompt sent to Whisper:
```
Meeting with: Shagun, Sankalp, Jagen, Nirmal.
```

This helps Whisper recognize these specific names during audio-to-text conversion.

### Layer 2: LLM Name Correction
During task extraction, the LLM prompt now includes:
- List of correct employee names
- Explicit instruction to correct misspellings
- Examples of common misspellings (Sangal → Sankalp, Normal → Nirmal, etc.)

## Adding New Employees

### Update `employees.json`
Add new team members to the file in the project root:

```json
[
  {
    "email": "john@company.com",
    "name": "John",
    "roles": ["Engineer"],
    "skills": ["Python"],
    "capacity": 0.7
  }
]
```

**Important**: Only the `name` field is required for name recognition. Other fields are optional.

### Current Team Members
- Shagun
- Sankalp (was being transcribed as "Sangal")
- Jagen (was being transcribed as "Jagan")
- Nirmal (was being transcribed as "Normal")

## Testing the Changes

### 1. Test Transcription
```bash
python scripts/transcribe.py audio.wav --model base
```

You should see:
```
Loaded 4 employee names for transcription hints: Shagun, Sankalp, Jagen, Nirmal
```

### 2. Test Task Extraction
```bash
python scripts/extract_tasks.py transcript.json --meeting_date 2025-12-29
```

You should see:
```
Using employee names: Shagun, Sankalp, Jagen, Nirmal
```

### 3. Full Pipeline Test
Upload a new meeting recording through the web UI and check:
- Transcript should have better name recognition
- Tasks should use correct spellings in the `assignee` field

## Files Modified

1. **`employees.json`** - Updated with actual team members
2. **`scripts/transcribe.py`** - Added employee name hints to Whisper
3. **`scripts/extract_tasks.py`** - Added employee names to LLM prompt

## Limitations

- **Whisper hints are not perfect**: Very similar-sounding names may still be confused
- **Works best with**: Distinct names that sound different
- **Accent sensitivity**: Heavy accents may still cause issues
- **Post-processing helps**: The LLM correction layer catches most remaining errors

## Future Improvements

1. **Speaker Diarization**: Identify who is speaking (requires pyannote.audio)
2. **Custom Vocabulary**: Train a custom Whisper model with your team's names
3. **Phonetic Matching**: Add fuzzy matching for very similar names
4. **Feedback Loop**: Learn from corrections over time

## Deployment Notes

The changes are backward compatible and will work in production once deployed to Render.
