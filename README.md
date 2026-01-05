# 🎥 Laneway Meet AI Agent

A powerful, AI-driven web application designed to streamline post-meeting workflows. This tool automatically ingests meeting recordings, generates accurate transcripts, identifies action items, and assigns them to team members.

![Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)
![Redis](https://img.shields.io/badge/Cache-Redis-red)

## ✨ Features

- **🚀 Smart Transcription**: Uses **Faster-Whisper** for high-performance, local speech-to-text conversion. Capable of running heavily optimized inference on CPU/GPU.
- **⚡ Intelligent Caching**: Integrated **Redis** caching layer ensures that previously processed files are retrieved instantly, saving time and compute resources.
- **📝 Action Item Extraction**: Leverages LLMs (OpenAI GPT) to parse transcripts and extract concrete tasks, deadlines, and owners.
- **🤖 Google Drive Automation**: Automatically pulls daily meeting recordings from Google Drive folders.
- **📤 Notion Integration**: Syncs extracted tasks to department-specific Notion databases automatically.
- **⏰ Scheduled Processing**: Set it and forget it - runs daily at your preferred time.
- **🎨 Modern UI**: A sleek, responsive dark-mode web interface for easy file uploads and result viewing.
- **📂 Wide Format Support**: Ingests `mp4`, `wav`, and other common media formats via `ffmpeg`.


## 🛠️ Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla HTML5 / CSS3 (Responsive Design)
- **AI/ML**: 
  - `faster-whisper` (Local Transcription)
  - `openai-gpt` (Task Extraction)
- **Infrastructure**:
  - Redis (Caching)
  - FFmpeg (Audio Processing)
  - Docker (Containerization)

## 🚀 Getting Started

### Prerequisites

1.  **Python 3.10+** installed.
2.  **FFmpeg** installed and added to system PATH.
3.  **Redis Server** running locally (e.g., via Memurai on Windows or Docker).

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/shagunverma-04/laneway-meet-ai-agent.git
    cd laneway-meet-ai-agent
    ```

2.  **Set up Virtual Environment:**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Mac/Linux
    source .venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment:**
    Create a `.env` file in the root directory:
    ```env
    OPENAI_API_KEY=sk-your-api-key-here
    ```

### Running the Application

1.  **Ensure Redis is running** (Default: localhost:6379).
2.  **Start the Server:**
    ```bash
    python app.py
    ```
3.  **Access the UI:**
    Open your browser and navigate to `http://localhost:8000`.

## 🐳 Deployment

The application is container-ready and includes a `Dockerfile`.

### Deploying to Render/Cloud
1.  **Database**: Ensure you have a Redis instance available (e.g., Render Redis).
2.  **Environment Variables**: Set `OPENAI_API_KEY` and any Redis configuration variables needed.
3.  **Build Command**: `pip install -r requirements.txt`
4.  **Start Command**: `python app.py` (or `uvicorn app:app --host 0.0.0.0 --port $PORT`)

## 📂 Project Structure

- `scripts/transcribe.py`: Logic for Whisper transcription (supports Local & API).
- `scripts/extract_tasks.py`: LLM-based task extraction logic.
- `scripts/sync_to_notion.py`: Notion database integration.
- `scripts/google_drive_sync.py`: Google Drive automation.
- `scripts/daily_automation.py`: Complete automation workflow.
- `index.html` & `styles.css`: Frontend user interface.
- `requirements.txt`: Project dependencies.

## 🤖 Automation

### Quick Start
```bash
# Run setup wizard
python setup.py

# Test automation
python scripts/scheduler.py --run-now

# Schedule daily at 9 AM
python scripts/scheduler.py --time 09:00
```

### Documentation
- **[Quick Start Guide](QUICKSTART.md)** - Get up and running in 5 minutes
- **[Google Drive Automation](GOOGLE_DRIVE_AUTOMATION.md)** - Complete automation setup
- **[Notion Integration](NOTION_AUTOMATION.md)** - Notion database configuration

