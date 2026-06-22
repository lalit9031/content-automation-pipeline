#!/usr/bin/env python3
"""
comfy_resource_guard.py
A lightweight, zero-dependency background daemon that monitors the local ComfyUI server.
If the server has been idle (no active or pending queue jobs) for a specified period (e.g., 60s),
it automatically terminates the process to free up VRAM and system memory for other tasks.
"""

import time
import urllib.request
import json
import subprocess
import os
import sys

def get_comfyui_pid():
    """Finds the Process ID (PID) of the running ComfyUI main.py instance."""
    if sys.platform == "win32":
        try:
            # query WMIC for the process matching ComfyUI\main.py command line
            cmd = 'wmic process where "CommandLine like \'%ComfyUI\\\\main.py%\'" get ProcessId'
            output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
            lines = [line.strip() for line in output.strip().split('\n') if line.strip()]
            # First line is header, remaining are PIDs
            if len(lines) > 1:
                pids = [int(p) for p in lines[1:] if p.isdigit()]
                if pids:
                    return pids[0]
        except Exception:
            pass
    return None

def is_comfyui_idle():
    """Queries ComfyUI's queue status. Returns True if there are no running or pending jobs."""
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8188/queue", timeout=3)
        data = json.loads(req.read().decode('utf-8'))
        running = len(data.get("queue_running", []))
        pending = len(data.get("queue_pending", []))
        return (running == 0) and (pending == 0)
    except Exception:
        # If we can't connect, we assume it's idle or offline
        return True

def main():
    # Number of seconds ComfyUI can remain idle before being shut down
    IDLE_TIMEOUT_SECONDS = 60
    CHECK_INTERVAL_SECONDS = 5
    
    idle_since = None
    
    print("=" * 70)
    print("ComfyUI Resource Guard Daemon Active")
    print(f"- Idle Timeout: {IDLE_TIMEOUT_SECONDS}s")
    print(f"- Check Interval: {CHECK_INTERVAL_SECONDS}s")
    print("=" * 70)
    
    while True:
        pid = get_comfyui_pid()
        if pid:
            if is_comfyui_idle():
                if idle_since is None:
                    idle_since = time.time()
                    print(f"[Resource Guard] ComfyUI (PID {pid}) detected idle. Starting countdown...")
                else:
                    elapsed = time.time() - idle_since
                    if elapsed >= IDLE_TIMEOUT_SECONDS:
                        print(f"[Resource Guard] ComfyUI has been idle for {elapsed:.0f}s. Releasing VRAM/RAM...")
                        try:
                            if sys.platform == "win32":
                                subprocess.run(f"taskkill /PID {pid} /F", shell=True, check=True)
                            else:
                                os.kill(pid, 9)
                            print("[Resource Guard] Successfully terminated ComfyUI server process.")
                        except Exception as e:
                            print(f"[Resource Guard] Failed to terminate process {pid}: {e}")
                        idle_since = None
            else:
                if idle_since is not None:
                    print("[Resource Guard] ComfyUI has active jobs. Resetting countdown.")
                    idle_since = None
        else:
            if idle_since is not None:
                idle_since = None
                
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
