# Speaker Diarization Script
# Adds speaker labels to an existing transcript using pyannote.audio
# Usage: python scripts/add_speakers.py transcript.json --output transcript_with_speakers.json

import argparse
import json
import os
import sys
from pathlib import Path

def load_employee_names():
    """Load employee names from employees.json."""
    try:
        base_dir = Path(__file__).parent.parent
        employees_file = base_dir / "employees.json"
        
        if not employees_file.exists():
            return []
        
        with open(employees_file, 'r') as f:
            employees = json.load(f)
        
        names = [emp.get("name") for emp in employees if emp.get("name")]
        return names
    except Exception as e:
        print(f"Warning: Could not load employee names: {e}", file=sys.stderr)
        return []

def add_speaker_diarization(audio_path, transcript, employee_names=None):
    """
    Add speaker labels to transcript using pyannote.audio.
    Requires HuggingFace token for pyannote models.
    """
    try:
        from pyannote.audio import Pipeline
        import torch
    except ImportError:
        print("ERROR: pyannote.audio not installed.", file=sys.stderr)
        print("Install with: pip install pyannote.audio", file=sys.stderr)
        print("You'll also need a HuggingFace token from: https://huggingface.co/settings/tokens", file=sys.stderr)
        return transcript
    
    # Get HuggingFace token
    hf_token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    if not hf_token:
        print("ERROR: HUGGINGFACE_TOKEN not set.", file=sys.stderr)
        print("Get a token from: https://huggingface.co/settings/tokens", file=sys.stderr)
        print("Then set: export HUGGINGFACE_TOKEN=your_token_here", file=sys.stderr)
        return transcript
    
    print("Loading speaker diarization model...")
    try:
        # Load the speaker diarization pipeline
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )
        
        # Run diarization
        print(f"Running speaker diarization on {audio_path}...")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline.to(device)
        
        diarization = pipeline(audio_path)
        
        # Create a mapping of time ranges to speakers
        speaker_timeline = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_timeline.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker
            })
        
        print(f"Found {len(set([s['speaker'] for s in speaker_timeline]))} unique speakers")
        
        # Match transcript segments to speakers
        for segment in transcript:
            seg_start = segment["start"]
            seg_end = segment["end"]
            seg_mid = (seg_start + seg_end) / 2
            
            # Find the speaker at the midpoint of this segment
            speaker_label = None
            for turn in speaker_timeline:
                if turn["start"] <= seg_mid <= turn["end"]:
                    speaker_label = turn["speaker"]
                    break
            
            # If no exact match, find the closest speaker
            if not speaker_label and speaker_timeline:
                closest = min(speaker_timeline, key=lambda x: abs((x["start"] + x["end"]) / 2 - seg_mid))
                speaker_label = closest["speaker"]
            
            segment["speaker"] = speaker_label or "Unknown"
        
        # Optionally: Try to map speaker labels to employee names
        # This is a simple heuristic - you might want to improve this
        if employee_names:
            print("Attempting to map speakers to employee names...")
            # For now, just use the speaker labels as-is
            # A more sophisticated approach would use voice embeddings or manual mapping
        
        return transcript
        
    except Exception as e:
        print(f"ERROR: Speaker diarization failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return transcript

def simple_speaker_detection(transcript, employee_names):
    """
    Simple speaker detection based on name mentions in the text.
    This is a fallback when pyannote is not available.
    """
    print("Using simple name-based speaker detection (fallback)...")
    
    current_speaker = None
    for segment in transcript:
        text = segment.get("text", "").lower()
        
        # Check if any employee name is mentioned
        mentioned_name = None
        for name in employee_names:
            if name.lower() in text:
                mentioned_name = name
                break
        
        # If a name is mentioned, assume they're speaking
        if mentioned_name:
            current_speaker = mentioned_name
        
        segment["speaker"] = current_speaker or "Unknown"
    
    return transcript

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add speaker labels to transcript")
    parser.add_argument("transcript", help="Path to transcript.json")
    parser.add_argument("--audio", help="Path to audio file (required for pyannote diarization)")
    parser.add_argument("--output", default="transcript_with_speakers.json", help="Output file")
    parser.add_argument("--simple", action="store_true", help="Use simple name-based detection instead of pyannote")
    args = parser.parse_args()
    
    # Load transcript
    with open(args.transcript, 'r') as f:
        transcript = json.load(f)
    
    print(f"Loaded transcript with {len(transcript)} segments")
    
    # Load employee names
    employee_names = load_employee_names()
    print(f"Loaded {len(employee_names)} employee names: {', '.join(employee_names)}")
    
    # Add speaker labels
    if args.simple or not args.audio:
        transcript = simple_speaker_detection(transcript, employee_names)
    else:
        transcript = add_speaker_diarization(args.audio, transcript, employee_names)
    
    # Save updated transcript
    with open(args.output, 'w') as f:
        json.dump(transcript, f, indent=2)
    
    print(f"Saved transcript with speaker labels to {args.output}")
    
    # Print summary
    speakers = set([seg.get("speaker", "Unknown") for seg in transcript])
    print(f"\nFound {len(speakers)} unique speakers: {', '.join(sorted(speakers))}")
