# KidsStudio-Orchestrator

A dynamic, data-driven 2D children's storytelling video generation pipeline powered by the Gemini API, automated lip-syncing (Rhubarb), and local rendering engines.

---

## 🛠️ VS Code Developer Setup

When you open this project in **VS Code**, a popup notification will automatically appear asking:
> *"This repository contains recommended extensions. Do you want to install them?"*

Click **Install All** to automatically set up the recommended tools.

### Recommended Extensions (Manual List):
* **Python** (`ms-python.python`) — Core Python execution and debugging.
* **Pylance** (`ms-python.vscode-pylance`) — Code autocomplete, types, and imports.
* **GitLens** (`eamodio.gitlens`) — Visual Git history and blame annotations.
* **Markdown All in One** (`yzhang.markdown-all-in-one`) — For rendering manifests and planning guides.

---

## ⚙️ System Prerequisites

Before running the code, ensure the following system-level tools are installed on your machine:

### 1. Python 3.10 or higher
Download and install Python from the official site, or install it via Homebrew on macOS:
```bash
brew install python
```

### 2. FFmpeg (Critical for Video Processing)
FFmpeg is used for stitching images, extracting audio, and mastering background tracks.
* **macOS:** Install via Homebrew:
  ```bash
  brew install ffmpeg
  ```
* **Windows:** Install via winget or download from the official page:
  ```cmd
  winget install Gnu.FFmpeg
  ```
* **Linux:** Install via apt:
  ```bash
  sudo apt update && sudo apt install ffmpeg
  ```

### 3. Rhubarb Lip Sync Binary
* The macOS executable is already bundled and configured in `bin/rhubarb`.
* **If on Windows or Linux:** Download the appropriate Rhubarb release from [Rhubarb Lip Sync releases](https://github.com/DanielSWolf/rhubarb-lip-sync/releases) and replace the file at `./bin/rhubarb` (or `./bin/rhubarb.exe` for Windows).

---

## 🚀 Getting Started

Follow these steps to set up and run the project locally:

### 1. Initialize Virtual Environment & Dependencies
Navigate to the project root directory and run:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment (macOS/Linux)
source .venv/bin/activate

# Activate virtual environment (Windows cmd)
.venv\Scripts\activate

# Install required python packages
pip install -r requirements.txt
```

### 2. Configure Environment variables
Create a `.env` file at the root of the project (or ensure your environment has the keys loaded) and add your active Google AI Studio Gemini API Key:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Compile the Video
To compile our showcase project **"Ghamandi Mor"**, run the compiler script:
```bash
python src/video_pipeline/scene_compiler.py
```

---

## 🧹 Storage Lifecycle & Housekeeping
To prevent your SSD from filling up, the compiler runs an automated **3-day global housekeeping cycle** that wipes out loose temp files under the scratch folder while keeping active directories safe. 

* The final Master videos are compiled and exported directly to your designated storage path: `/Volumes/Crucial X9/Mac/2D_Video`.
