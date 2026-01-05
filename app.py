from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import shutil, os, subprocess, json, sys, hashlib, redis
from pathlib import Path

# Try to load .env file if python-dotenv is available.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, that's okay.

# Initialize Redis client (optional - for caching)
# We use decode_responses=True so we get strings instead of bytes
redis_client = None
try:
    # Get Redis URL from environment variable, default to localhost for local dev
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    
    # Parse Redis URL if it's a full URL
    if redis_url.startswith('redis://'):
        redis_client = redis.from_url(redis_url, decode_responses=True)
    else:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    # Test the connection
    redis_client.ping()
    print("✓ Redis connected successfully")
except Exception as e:
    print(f"⚠ Redis not available (caching disabled): {e}")
    redis_client = None

app = FastAPI()
BASE_DIR = Path(__file__).parent

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.head("/")  # Support HEAD requests for health checks
async def read_root():
    """Serve the index.html file at the root path."""
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)

@app.get("/styles.css")
async def read_css():
    """Serve the styles.css file."""
    css_path = BASE_DIR / "styles.css"
    if not css_path.exists():
        raise HTTPException(status_code=404, detail="styles.css not found")
    return FileResponse(css_path)

@app.post("/ingest/")
async def ingest(file: UploadFile = File(...)):
    dst = BASE_DIR / file.filename
    with open(dst, "wb") as f:
        shutil.copyfileobj(file.file, f)
    # In production: push to cloud storage, emit a job to queue.
    return {"status":"uploaded","filename":file.filename}

def calculate_file_hash(filepath: Path):
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        # Read in chunks to avoid memory issues
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

@app.post("/process/")
async def process(filename: str = Form(...), background: BackgroundTasks = BackgroundTasks()):
    """
    Full processing pipeline for an uploaded media file.

    Optimizations for latency:
    - Do audio extraction + transcription synchronously (so the user gets the transcript quickly).
    - Run task extraction in a FastAPI BackgroundTask so we don't block the response.
    """
    print(f"[PROCESS] Starting processing for: {filename}")
    filepath = BASE_DIR / filename
    if not filepath.exists():
        print(f"[PROCESS] ERROR: File not found: {filepath}")
        return {"status":"processing_failed", "error":"File not found"}
    audio_path = BASE_DIR / "audio.wav"
    transcript_path = BASE_DIR / "transcript.json"

    # 1. Calculate Hash
    print(f"[PROCESS] Calculating file hash...")
    file_hash = calculate_file_hash(filepath)
    print(f"[PROCESS] File hash: {file_hash}")
    
    # 2. Check Redis Cache
    if redis_client:
        try:
            print(f"[PROCESS] Checking Redis cache...")
            cached_transcript = redis_client.get(file_hash)
            if cached_transcript:
                print(f"[PROCESS] Cache HIT for {filename}")
                # Write cached transcript to file so existing flow works
                with open(transcript_path, "w", encoding="utf-8") as f:
                    f.write(cached_transcript)
                
                # We still need to run task extraction (it's fast), or we could cache that too?
                # The user only asked for faster processing (implied transcription).
                # The task extraction reads transcript.json, so we are good.
                
                # Trigger task extraction in background
                def run_extract_tasks_cached():
                    extract_script = BASE_DIR / "scripts" / "extract_tasks.py"
                    try:
                        env = os.environ.copy()
                        result = subprocess.run(
                            [sys.executable, str(extract_script), "transcript.json", "--meeting_date", "2025-12-01"],
                            check=False,
                            cwd=str(BASE_DIR),
                            env=env,
                            capture_output=True,
                            text=True
                        )
                        if result.returncode == 0:
                            print(f"Task extraction completed successfully (cached)", file=sys.stdout)
                            
                            # Auto-sync to Notion if enabled
                            try:
                                from notion_sync_helper import sync_tasks_to_notion
                                sync_tasks_to_notion()
                            except Exception as e:
                                print(f"[NOTION] Sync failed: {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"Task extraction error: {str(e)}", file=sys.stderr)
                
                background.add_task(run_extract_tasks_cached)
                
                return {"status":"processing_completed", "cached": True}
        except Exception as e:
            print(f"[PROCESS] Redis cache error: {e}")
    
    # Delete old transcript if it exists
    if transcript_path.exists():
        transcript_path.unlink()
    
    try:
        # extract audio
        print(f"[PROCESS] Extracting audio with ffmpeg...")
        ffmpeg_result = subprocess.run(
            ["ffmpeg","-y","-i", str(filepath), "-vn","-acodec","pcm_s16le","-ar","16000","-ac","1", str(audio_path)], 
            check=False,
            capture_output=True,
            text=True
        )
        if ffmpeg_result.returncode != 0:
            print(f"[PROCESS] ERROR: Audio extraction failed")
            return {"status":"processing_failed", "error":f"Audio extraction failed: {ffmpeg_result.stderr[:200]}"}
        
        print(f"[PROCESS] Audio extracted successfully")
        # transcribe (calls script)
        print(f"[PROCESS] Starting transcription...")
        transcribe_script = BASE_DIR / "scripts" / "transcribe.py"
        # Ensure environment variables are passed to subprocess and use the same Python interpreter
        # Use "base" model for better accuracy (GPU can handle it efficiently)
        env = os.environ.copy()
        transcribe_result = subprocess.run(
            [sys.executable, str(transcribe_script), str(audio_path), "--model", "base"], 
            check=False,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            env=env  # Pass environment variables explicitly
        )
        if transcribe_result.returncode != 0:
            # Transcription failed, ensure transcript.json doesn't exist
            print(f"[PROCESS] ERROR: Transcription failed")
            if transcript_path.exists():
                transcript_path.unlink()
            # Combine both stdout and stderr for better error messages
            error_msg = ""
            if transcribe_result.stderr:
                error_msg += f"STDERR: {transcribe_result.stderr}"
            if transcribe_result.stdout:
                error_msg += f" STDOUT: {transcribe_result.stdout}"
            if not error_msg:
                error_msg = "Unknown error"
            
            # Check if API key is set
            api_key_set = bool(os.environ.get("OPENAI_API_KEY"))
            whisper_installed = False
            try:
                import whisper
                whisper_installed = True
            except:
                pass
            
            return {
                "status":"processing_failed", 
                "error":f"Transcription failed: {error_msg[:800]}. API Key Set: {api_key_set}, Whisper Installed: {whisper_installed}"
            }
        
        print(f"[PROCESS] Transcription completed successfully")
        # Verify transcript was created
        if not transcript_path.exists():
            print(f"[PROCESS] ERROR: Transcript file not created")
            return {"status":"processing_failed", "error":"Transcription completed but transcript file was not created"}
        
        # Cache the result in Redis
        if redis_client:
            try:
                print(f"[PROCESS] Caching transcript in Redis...")
                with open(transcript_path, "r", encoding="utf-8") as Tf:
                    transcript_data = Tf.read()
                redis_client.set(file_hash, transcript_data)
                print(f"[PROCESS] Cached transcript for {filename}")
            except Exception as e:
                print(f"[PROCESS] Failed to cache transcript: {e}")

        # Extract tasks in a background task so we don't block /process latency.
        # This means the transcript becomes available first, and tasks.json shortly after.
        def run_extract_tasks():
            extract_script = BASE_DIR / "scripts" / "extract_tasks.py"
            try:
                env = os.environ.copy()
                result = subprocess.run(
                    [sys.executable, str(extract_script), "transcript.json", "--meeting_date", "2025-12-01"],
                    check=False,
                    cwd=str(BASE_DIR),
                    env=env,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    print(f"Task extraction failed: {result.stderr}", file=sys.stderr)
                else:
                    print(f"Task extraction completed successfully", file=sys.stdout)
                    
                    # Auto-sync to Notion if enabled
                    try:
                        from notion_sync_helper import sync_tasks_to_notion
                        sync_tasks_to_notion()
                    except Exception as e:
                        print(f"[NOTION] Sync failed: {e}", file=sys.stderr)
                        
            except Exception as e:
                print(f"Task extraction error: {str(e)}", file=sys.stderr)

        background.add_task(run_extract_tasks)
        
        print(f"[PROCESS] Processing completed successfully for {filename}")
        return {"status":"processing_completed"}
    except Exception as e:
        print(f"[PROCESS] FATAL ERROR: {str(e)}")
        return {"status":"processing_failed", "error":f"Processing error: {str(e)}"}

@app.get("/health")
def health():
    return {"status":"ok"}

@app.get("/config/")
def get_config():
    """Check configuration status."""
    has_whisper = False
    cuda_available = False
    gpu_name = None
    try:
        import whisper
        has_whisper = True
    except ImportError:
        pass
    
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    
    has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))
    
    return {
        "whisper_installed": has_whisper,
        "openai_api_key_set": has_openai_key,
        "transcription_available": has_whisper or has_openai_key,
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "message": "Ready for transcription" if (has_whisper or has_openai_key) else "No transcription method available. Install Whisper or set OPENAI_API_KEY"
    }

@app.get("/transcript/")
def get_transcript():
    """Retrieve the generated transcript."""
    transcript_path = BASE_DIR / "transcript.json"
    if not transcript_path.exists():
        return {"status": "not_ready", "transcript": None}
    
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = json.load(f)
    except json.JSONDecodeError as e:
        return {"status": "error", "transcript": None, "error": f"Invalid transcript file: {str(e)}"}
    except Exception as e:
        return {"status": "error", "transcript": None, "error": f"Error reading transcript: {str(e)}"}
    
    # Validate transcript structure
    if not isinstance(transcript, list):
        return {"status": "error", "transcript": None, "error": f"Invalid transcript format: expected a list, got {type(transcript).__name__}"}
    
    if len(transcript) == 0:
        return {"status": "error", "transcript": None, "error": "Transcript is empty"}

    for i, seg in enumerate(transcript):
        if not isinstance(seg, dict):
            return {"status": "error", "transcript": None, "error": f"Invalid segment at index {i}: expected dict, got {type(seg).__name__}"}
        if "text" not in seg:
            return {"status": "error", "transcript": None, "error": f"Segment at index {i} missing 'text' field"}
        if "start" not in seg:
            seg["start"] = 0.0
        if "end" not in seg:
            seg["end"] = 0.0
    
    
    dummy_texts = [
        "We need to create onboarding mockups by next Monday.",
        "Sanya will take that.",
        "Also, backend should add analytics events."
    ]
    if len(transcript) == 3:
        transcript_texts = [seg.get("text", "") for seg in transcript if isinstance(seg, dict)]
        if all(any(dummy_text in txt for txt in transcript_texts) for dummy_text in dummy_texts):
            # This is dummy data, return error
            return {"status": "error", "transcript": None, "error": "Transcription failed. Options: 1) Install Whisper: pip install -U openai-whisper, or 2) Set OPENAI_API_KEY environment variable to use OpenAI API"}
    
    return {"status": "ready", "transcript": transcript}

@app.get("/tasks/")
def get_tasks():
    """Retrieve the extracted tasks."""
    tasks_path = BASE_DIR / "tasks.json"
    if not tasks_path.exists():
        raise HTTPException(status_code=404, detail="Tasks not found. Please process a file first.")
    with open(tasks_path, "r") as f:
        tasks = json.load(f)
    return {"tasks": tasks}
