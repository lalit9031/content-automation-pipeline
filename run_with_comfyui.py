#!/usr/bin/env python3
"""
run_with_comfyui.py
Wrapper script to automatically start the ComfyUI server, run a generation script,
and terminate the ComfyUI server immediately after completion to free up VRAM/RAM.
"""

import subprocess
import time
import urllib.request
import urllib.error
import sys
from pathlib import Path

def is_comfyui_running():
    try:
        # Check if the server is responsive
        urllib.request.urlopen("http://127.0.0.1:8188", timeout=2)
        return True
    except Exception:
        return False

def start_comfyui():
    print("[Optimized Runtime] Starting ComfyUI server in the background...")
    import os
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:256"
    cmd = [
        r"C:\ComfyUI\procgov.exe",
        "--maxmem", "25G",
        "--",
        r"C:\ComfyUI\python_embeded\python.exe",
        "-s",
        r"C:\ComfyUI\ComfyUI\main.py",
        "--windows-standalone-build",
        "--enable-dynamic-vram",
        "--lowvram",
        "--fp8_e4m3fn"
    ]
    # Write logs to a file to keep the console output clean
    log_path = Path("comfyui_server_runtime.log")
    log_file = open(log_path, "w", encoding="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if sys.platform == "win32":
        flags |= 0x00000040 # IDLE_PRIORITY_CLASS
    proc = subprocess.Popen(
        cmd,
        cwd=r"C:\ComfyUI",
        stdout=log_file,
        stderr=log_file,
        creationflags=flags
    )
    return proc, log_file

def wait_for_comfyui(timeout=120):
    start_time = time.time()
    print("[Optimized Runtime] Waiting for ComfyUI to start listening on port 8188...")
    while time.time() - start_time < timeout:
        if is_comfyui_running():
            print("[Optimized Runtime] ComfyUI server is up and listening!")
            return True
        time.sleep(2)
    print("[Optimized Runtime] Timeout waiting for ComfyUI server to start.")
    return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_with_comfyui.py <script_to_run.py> [args...]")
        sys.exit(1)
        
    script = sys.argv[1]
    script_args = sys.argv[2:]
    
    started_by_us = False
    proc = None
    log_file = None
    
    if is_comfyui_running():
        print("[Optimized Runtime] ComfyUI is already running. Using the existing instance.")
    else:
        proc, log_file = start_comfyui()
        started_by_us = True
        if not wait_for_comfyui():
            print("[Optimized Runtime] Error: ComfyUI server failed to start.")
            if proc:
                proc.terminate()
            sys.exit(1)
            
    try:
        # Run the specified script using the current Python executable
        python_exe = sys.executable or "python"
        cmd = [python_exe, script] + script_args
        print(f"[Optimized Runtime] Running script: {' '.join(cmd)}")
        result = subprocess.run(cmd)
        print(f"[Optimized Runtime] Script finished with exit code: {result.returncode}")
    finally:
        if started_by_us and proc:
            print("[Optimized Runtime] Terminating ComfyUI server to free RAM/VRAM...")
            # On Windows, we send CTRL_BREAK_EVENT to the process group or terminate directly
            proc.terminate()
            try:
                proc.wait(timeout=15)
                print("[Optimized Runtime] ComfyUI server terminated successfully. RAM/VRAM freed.")
            except subprocess.TimeoutExpired:
                print("[Optimized Runtime] ComfyUI server did not terminate in time. Force killing...")
                proc.kill()
                proc.wait()
                print("[Optimized Runtime] ComfyUI server force killed. RAM/VRAM freed.")
            
            if log_file:
                log_file.close()

if __name__ == "__main__":
    main()
