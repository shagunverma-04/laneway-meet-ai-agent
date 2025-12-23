# Merge diarization segments (speaker start/end) with transcript segments (start/end/text)
import json, argparse
def find_speaker(start, diar):
    for d in diar:
        if start >= d['start'] and start <= d['end']:
            return d['speaker']
    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('transcript', help='transcript.json')
    parser.add_argument('diarization', help='diar.json')
    parser.add_argument('--out', default='merged.json')
    args = parser.parse_args()
    with open(args.transcript) as f:
        trans = json.load(f)
    with open(args.diarization) as f:
        diar = json.load(f)
    merged = []
    for seg in trans:
        speaker = find_speaker(seg['start'], diar)
        merged.append({
            'speaker': speaker or 'Unknown',
            'start': seg['start'],
            'end': seg['end'],
            'text': seg['text']
        })
    with open(args.out, 'w') as f:
        json.dump(merged, f, indent=2)
    print('Saved merged to', args.out)
