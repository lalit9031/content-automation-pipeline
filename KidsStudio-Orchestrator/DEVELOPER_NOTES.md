# KidsStudio-Orchestrator Developer Notes

## 🧹 Automated 3-Day Workspace Janitor
To prevent local SSD storage from filling up with old generated assets, this project runs an automated global housekeeping sweep.

* **Trigger:** It runs automatically at the start of every video compilation command in [scene_compiler.py](file:///Users/lalitprasadsingh/.gemini/antigravity/scratch/KidsStudio-Orchestrator/src/video_pipeline/scene_compiler.py).
* **Schedule:** Checks the hidden timestamp file at `.last_global_cleanup` in the parent directory. If **3 days or more** have elapsed since the last run, it initiates a cleanup cycle.
* **Cleanup Target:** Deletes all loose media files (*.mp3, *.wav, *.mp4, *.png, *.svg) located directly under `/Users/lalitprasadsingh/.gemini/antigravity/scratch/` while leaving active workspaces (`KidsStudio-Orchestrator` and `content-automation-pipeline`) untouched.
* **Output storage rules:** From next time, large compiled project video files and render outputs should be targeting `/Volumes/Crucial X9/Mac/2D_Video` on the external drive.

## 🌿 Git Branch Strategy
To keep development aligned across multiple conversations and developers:
* **`content-automation-pipeline` Repo:** 
  * Active Branch: **`main1`** (tracks `origin/main1` on GitHub at `lalit9031/content-automation-pipeline`). 
  * Always pull/push changes on **`main1`**.
* **`KidsStudio-Orchestrator` Repo (This folder):**
  * Active Branch: **`main`** (local primary branch).
  * No remote is configured yet. When pushed to a remote repository, use **`main`**.
