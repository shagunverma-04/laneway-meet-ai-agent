# Usage: python scripts/extract_audio.py input.mp4 output.wav
import sys, subprocess
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: extract_audio.py input.mp4 output.wav")
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2]
    cmd = ["ffmpeg","-y","-i", inp, "-vn","-acodec","pcm_s16le","-ar","16000","-ac","1", out]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("Extracted audio to", out)
