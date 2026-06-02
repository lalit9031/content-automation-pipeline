import os
import sys
from pathlib import Path

# Insert src directory to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from content_pipeline.config import Settings
from content_pipeline.bots.auto_youtube import run_autonomous_creator_and_upload

def main():
    # Load settings from project environment
    settings = Settings.from_environment(PROJECT_ROOT)
    
    # We will override Settings to use 'gemini' as the primary voice provider
    # so we can show off the high-fidelity prebuilt neural voices!
    from dataclasses import replace
    settings = replace(
        settings, 
        voice_provider="gemini", 
        indian_tts_voice="Rasalgethi"
    )
    
    drive_folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1pXJjgcxgYQ65K3Gw5kOipHBR0ZpR25eK")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    
    print("==================================================================")
    print("🚀 LAUNCHING AUTONOMOUS CREATOR PIPELINE RUN...")
    print(f"📂 Google Drive Folder ID: {drive_folder}")
    print(f"🔑 Hugging Face Token Active: {bool(settings.hf_token)}")
    print(f"🎙️ Fallback Voice Provider: {settings.voice_provider}")
    print("==================================================================")
    
    try:
        res = run_autonomous_creator_and_upload(
            topic="A kids sci-fi adventure about a sudden gravity malfunction in a spaceship cockpit",
            voice_ref_name="shirt_color_voice.wav",
            avatar_choice="talking_avatar.gif",
            custom_avatar_path=None,
            aspect="Vertical Short (9:16)",
            settings=settings,
            log_callback=lambda msg: print(f"  👉 {msg}", flush=True),
            drive_folder_id=drive_folder,
            telegram_bot_token=tg_token,
            telegram_chat_id=tg_chat
        )
        
        print("\n==================================================================")
        print("🎉 PIPELINE SUCCESSFUL!")
        print(f"🎬 Title: {res.get('youtube_title')}")
        print(f"🎥 YouTube ID (Private): {res.get('youtube_id')}")
        print(f"📂 Google Drive link: {res.get('drive_link')}")
        print(f"📦 Stitched video MP4: {res.get('video_path')}")
        print("==================================================================")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
