# Local Workflow Persistence & Directory Structure Guide

This document explains how your local kid's story automation pipeline, models, and dependencies are structured on your machine, answering whether you need to reinstall anything if you move the codebase or if the AI session limit is reached.

---

## 🔍 Core Question
> *"If the AI daily usage limit gets exhausted, or if I pull the repository from Git into my own VS Code workspace folder, do I need to install everything again?"*

### **Answer: Absolutely Not!**

All the heavy components (models, servers, and Python dependencies) are installed **globally** or in **dedicated persistent directories outside the `.gemini` folder**. The `.gemini` directory only holds the temporary copies of the text/code files for the AI context. 

---

## 📂 System Directory Layout & Persistence

Here is exactly where each component is stored on your Windows machine:

| Component | Disk Location | Persistent? | Description |
| :--- | :--- | :---: | :--- |
| **ComfyUI Core** | `C:\ComfyUI\` | **YES** | Global standalone server. Completely safe from any session resets. |
| **LTX-Video Checkpoint** | `C:\ComfyUI\ComfyUI\models\checkpoints\ltxv-13b-0.9.8-dev-fp8.safetensors` | **YES** | The 14.6 GB video model. Saved permanently in your ComfyUI models directory. |
| **T5-XXL Text Encoder** | `C:\ComfyUI\ComfyUI\models\text_encoders\t5xxl_fp8_e4m3fn.safetensors` | **YES** | The 4.56 GB text encoder for video prompt processing. Saved permanently. |
| **Python Environment** | `C:\ComfyUI\python_embeded\` | **YES** | All required libraries (like `requests`, `opencv`, `gradio_client`, etc.) are installed directly into ComfyUI's embedded python. They remain installed forever. |
| **Ollama & LLM Models** | `C:\Users\user\.ollama\models\` | **YES** | Local Vision/LLM models (like `qwen2.5-vl`) are managed by the Ollama application, stored in your user profile folder. |
| **Pipeline Code** | `C:\Users\user\.gemini\antigravity\scratch\content-automation-pipeline-main\` | *Temporary* | This is the current working copy the AI assistant edits. |

---

## 🚀 How to Move the Code to Your VS Code Workspace

If you want to move the codebase to a standard projects directory (e.g. `C:\projects\content-automation-pipeline-main`) and use VS Code directly:

1. **Move or Clone the Code**:
   Clone your Git repository or copy the `content-automation-pipeline-main` directory from the `.gemini\antigravity\scratch\` folder to your preferred workspace path.
   
2. **Open in VS Code**:
   Open VS Code and choose `File -> Open Folder...` and select your new project path.

3. **Configure `.env`**:
   Ensure you copy the `.env` file from the current directory to the root of your new workspace folder. The `.env` file points to the local ComfyUI server:
   ```env
   COMFYUI_URL=http://127.0.0.1:8188
   COMFYUI_VIDEO_WORKFLOW=workflows/comfyui_ltxv_i2v_api.json
   ```

4. **Run the Pipeline**:
   Open a terminal in VS Code and run the scripts using ComfyUI's embedded Python interpreter. Since all packages are already installed there, you do not need to run `pip install`:
   ```powershell
   # Run your video request
   C:\ComfyUI\python_embeded\python.exe generate_video_request.py
   ```

No redownloads of checkpoints, no compilation delays, and no library package reinstalls are required!
