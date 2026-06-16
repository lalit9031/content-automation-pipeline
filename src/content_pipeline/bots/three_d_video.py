import os
import json
import time
import requests
import subprocess
import shutil
import streamlit as st
from pathlib import Path
from google import genai
from google.genai import types
from content_pipeline.config import Settings

def robust_delete_folder(folder: Path) -> None:
    """Robustly deletes a folder. If a file is locked, truncates it to 0 bytes."""
    if not folder.exists():
        return
    if folder.is_dir():
        for file in folder.iterdir():
            if file.is_file():
                try:
                    file.unlink()
                except Exception:
                    try:
                        file.write_bytes(b"")
                    except Exception:
                        pass
        try:
            shutil.rmtree(folder)
        except Exception:
            pass


# --- JSON TRUNCATION REPAIR TOOL ---
def repair_truncated_json_array(json_str: str) -> list:
    """
    Repair truncated JSON array of objects by discarding the trailing incomplete object
    and closing the array correctly.
    """
    json_str = json_str.strip()
    if not json_str:
        return []
        
    try:
        return json.loads(json_str)
    except Exception:
        pass
        
    # Attempt to locate the end of the last complete scene object
    last_brace_idx = json_str.rfind("}")
    if last_brace_idx == -1:
        return []
        
    repaired_str = json_str[:last_brace_idx + 1].strip()
    
    # Ensure it starts with bracket
    if not repaired_str.startswith("["):
        first_bracket = repaired_str.find("[")
        if first_bracket != -1:
            repaired_str = repaired_str[first_bracket:]
        else:
            repaired_str = "[" + repaired_str
            
    # Add trailing array bracket
    repaired_str = repaired_str + "]"
    
    try:
        return json.loads(repaired_str)
    except Exception:
        # If there's a trailing comma before the bracket, try cleaning it
        try:
            repaired_str_clean = repaired_str[:-2].strip()
            if repaired_str_clean.endswith(","):
                repaired_str_clean = repaired_str_clean[:-1].strip()
            repaired_str_clean += "]"
            return json.loads(repaired_str_clean)
        except Exception:
            return []

# --- LLM PROMPT WRITER WITH FALLBACK ---
def call_prompt_llm(settings: Settings, user_prompt: str, max_tokens: int = 1800) -> str:
    """
    Call Claude (Anthropic / OpenRouter) first. If it fails, fallback to Bedrock Nova,
    and then fallback to direct Gemini API keys.
    Specifies a dynamic max_tokens limit to fit requested story lengths.
    """
    keys = []
    if settings.anthropic_api_key:
        keys.append(settings.anthropic_api_key)
    for k in getattr(settings, "anthropic_api_keys", ()):
        if k and k not in keys:
            keys.append(k)
            
    for env_var in ["ANTHROPIC_API_KEY_1", "ANTHROPIC_API_KEY"]:
        val = os.environ.get(env_var)
        if val and val not in keys:
            keys.append(val)

    last_err = None
    for api_key in keys:
        if not api_key:
            continue
        try:
            if api_key.startswith("sk-or-v1-"):
                model = "~anthropic/claude-sonnet-latest"
                
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": max_tokens
                    },
                    timeout=45
                )
                if response.status_code == 200:
                    res_json = response.json()
                    choices = res_json.get('choices')
                    if choices and len(choices) > 0:
                        content = choices[0].get('message', {}).get('content')
                        if content and content.strip():
                            return content
                    raise Exception(f"OpenRouter response empty or invalid for model {model}: {response.text}")
                else:
                    raise Exception(f"OpenRouter error {response.status_code}: {response.text}")
            else:
                import anthropic
                model = settings.anthropic_model or "claude-3-5-sonnet-20241022"
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )
                content = message.content[0].text
                if content and content.strip():
                    return content
                raise Exception("Anthropic SDK returned empty text")
        except Exception as e:
            last_err = e
            continue

    # 2. Add extra fallbacks from the environment keys (StepFun, Gemini 3.5, Gemini 3.5 Lite, Gemini Flash/Pro Latest, Gemma 4, Gemini 3 Flash, MiniMax M3)
    extra_fallbacks = [
        ("FALLBACK_KEY_STEPFUN", "stepfun/step-3.7-flash"),
        ("FALLBACK_KEY_GEMINI_35", "google/gemini-3.5-flash"),
        ("FALLBACK_KEY_GEMINI_35", "google/gemini-2.5-flash"),
        ("FALLBACK_KEY_GEMINI_35_LITE", "google/gemini-2.5-flash-lite"),
        ("FALLBACK_KEY_GEMINI_35_LITE", "google/gemini-3.1-flash-lite"),
        ("FALLBACK_KEY_GEMINI_FLASH_LATEST", "google/gemini-2.5-flash"),
        ("FALLBACK_KEY_GEMINI_FLASH_LATEST", "google/gemini-3.5-flash"),
        ("FALLBACK_KEY_GEMINI_PRO_LATEST", "google/gemini-2.5-pro"),
        ("FALLBACK_KEY_GEMINI_PRO_LATEST", "google/gemini-3.1-pro-preview"),
        ("FALLBACK_KEY_GEMINI_PRO_LATEST", "google/gemini-pro"),
        ("FALLBACK_KEY_GEMMA4", "google/gemma-4-31b-it"),
        ("FALLBACK_KEY_GEMINI_3_FLASH", "google/gemini-3-flash-preview"),
        ("FALLBACK_KEY_MINIMAX_M3", "minimax/minimax-m3"),
    ]
    for env_var, model_name in extra_fallbacks:
        api_key = os.environ.get(env_var)
        if not api_key:
            continue
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": max_tokens
                },
                timeout=45
            )
            if response.status_code == 200:
                res_json = response.json()
                choices = res_json.get('choices')
                if choices and len(choices) > 0:
                    content = choices[0].get('message', {}).get('content')
                    if content and content.strip():
                        return content
                raise Exception(f"OpenRouter response empty or invalid for model {model_name}: {response.text}")
            else:
                last_err = Exception(f"OpenRouter ({model_name}) error {response.status_code}: {response.text}")
        except Exception as e:
            last_err = e
            continue

    # 3. Fallback to Bedrock Nova
    try:
        import boto3
        from botocore.config import Config
        
        region = os.environ.get("AWS_REGION", "ap-southeast-2")
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        
        response = client.converse(
            modelId="global.amazon.nova-2-lite-v1:0",
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_prompt}],
                }
            ],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": 0.3,
            },
        )
        
        output = response.get("output")
        if not output:
            raise ValueError("Bedrock output is empty")
        message = output.get("message")
        if not message:
            raise ValueError("Bedrock message is empty")
        content = message.get("content")
        if not content or not isinstance(content, list):
            raise ValueError("Bedrock message content is empty")
        text_content = content[0].get("text", "")
        if text_content and text_content.strip():
            return text_content
        raise ValueError("Bedrock returned empty text content")
    except Exception as e:
        last_err = e

    # 4. Fallback to direct Gemini API keys (using official Google GenAI SDK)
    gemini_keys = []
    for slot in ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 11)]:
        val = os.environ.get(slot)
        if val and val.strip() and not val.startswith("AQ.Ab8RN6InHPLoj"):
            gemini_keys.append((slot, val.strip()))
            
    for slot, api_key in gemini_keys:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.3,
                )
            )
            if response.text and response.text.strip():
                return response.text
            raise Exception(f"Gemini API returned empty text content for slot {slot}")
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise Exception(f"All storyboard generation fallbacks failed. Last error: {last_err}")
    raise Exception("All storyboard generation fallbacks failed.")

# --- GOOGLE VEO GENERATOR ---
def generate_google_veo_clip(prompt: str, duration: int, output_path: Path, log_callback) -> bool:
    gemini_keys = []
    for slot in ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 11)]:
        val = os.environ.get(slot)
        if val and val.strip() and not val.startswith("AQ.Ab8RN6InHPLoj"):
            gemini_keys.append((slot, val.strip()))
            
    if not gemini_keys:
        log_callback("❌ No valid Gemini API keys found in environment setup.")
        return False
        
    for slot, api_key in gemini_keys:
        log_callback(f"🔑 Trying Gemini Key {slot} ({api_key[:8]}...)...")
        configs_to_try = [
            {"duration_seconds": 10, "resolution": "1080p"},
            {"duration_seconds": 8, "resolution": "720p"}
        ]
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            log_callback(f"⚠️ Failed to create client for Key {slot}: {str(e)[:150]}")
            continue

        for conf in configs_to_try:
            dur = conf["duration_seconds"]
            res = conf["resolution"]
            log_callback(f"⏳ Attempting Veo generation with {dur}s @ {res}...")
            try:
                operation = client.models.generate_videos(
                    model="veo-3.0-fast-generate-001",
                    prompt=prompt,
                    config=types.GenerateVideosConfig(
                        duration_seconds=dur,
                        aspect_ratio="16:9",
                        resolution=res
                    )
                )
                log_callback(f"⏳ Task started: `{operation.name}`. Polling for completion...")
                start_time = time.time()
                while not operation.done:
                    time.sleep(10)
                    elapsed = int(time.time() - start_time)
                    log_callback(f"⏳ Polling operation... ({elapsed}s elapsed)")
                    operation = client.operations.get(operation)
                    
                response = operation.response
                videos = getattr(response, "generated_videos", None) or []
                if videos:
                    video = videos[0]
                    video_bytes = client.files.download(file=video.video)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(video_bytes)
                    log_callback(f"✅ Success! Saved to `{output_path.name}` ({dur}s @ {res}).")
                    return True
                else:
                    log_callback(f"⚠️ Key {slot} with {dur}s @ {res} succeeded but returned no videos.")
            except Exception as e:
                log_callback(f"⚠️ Config failed ({dur}s @ {res}): {str(e)[:150]}")
                continue
            
    return False

# --- MINIMAX VEO FALLBACK GENERATOR (via OpenRouter) ---
def generate_minimax_video_clip(prompt: str, duration: int, output_path: Path, log_callback) -> bool:
    openrouter_keys = []
    # Prioritize keys: primary minimax key, fallback minimax keys, and then other OpenRouter slots
    for env_var in [
        "MINIMAX_API_KEY",
        "FALLBACK_KEY_MINIMAX_M3",
        "FALLBACK_KEY_GEMMA4",
        "FALLBACK_KEY_GEMINI_3_FLASH",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY_1",
        "FALLBACK_KEY_GEMINI_35_LITE",
        "FALLBACK_KEY_GEMINI_FLASH_LATEST",
        "FALLBACK_KEY_GEMINI_PRO_LATEST",
    ]:
        val = os.environ.get(env_var)
        if val and val.strip() and val.startswith("sk-or-v1-"):
            k = val.strip()
            if k not in openrouter_keys:
                openrouter_keys.append(k)

    if not openrouter_keys:
        log_callback("❌ No active OpenRouter keys found in environment to use for MiniMax video generation.")
        return False
        
    # Fallbacks for MiniMax: try 10s @ 1080p, then 6s @ 1080p
    configs_to_try = [
        {"duration": 10, "resolution": "1080p"},
        {"duration": 6, "resolution": "1080p"}
    ]

    for key_idx, minimax_key in enumerate(openrouter_keys):
        log_callback(f"🔑 Trying OpenRouter Key slot {key_idx+1}/{len(openrouter_keys)} ({minimax_key[:8]}...)...")
        headers = {
            "Authorization": f"Bearer {minimax_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/google/antigravity",
            "X-Title": "Antigravity 3D Video Studio"
        }
        
        key_failed = False
        for conf in configs_to_try:
            dur = conf["duration"]
            res = conf["resolution"]
            log_callback(f"⏳ Attempting MiniMax generation with {dur}s @ {res}...")
            
            payload = {
                "model": "minimax/hailuo-2.3",
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "duration": dur,
                "resolution": res
            }
            
            try:
                log_callback("🔑 Submitting MiniMax video task to OpenRouter...")
                response = requests.post("https://openrouter.ai/api/v1/videos", headers=headers, json=payload, timeout=30)
                if response.status_code != 200:
                    log_callback(f"⚠️ MiniMax config {dur}s @ {res} submit failed (Status {response.status_code}): {response.text}")
                    if response.status_code in (401, 402, 403) or "credit" in response.text.lower():
                        log_callback("⚠️ Credit or Authentication error on current key. Switching keys...")
                        key_failed = True
                        break
                    continue
                    
                job_data = response.json()
                job_id = job_data.get("id")
                if not job_id:
                    log_callback(f"⚠️ No job ID found in response payload: {job_data}")
                    continue
                    
                polling_url = f"https://openrouter.ai/api/v1/videos/{job_id}"
                log_callback(f"⏳ Task submitted! Job ID: `{job_id}`. Polling status...")
                start_time = time.time()
                
                while time.time() - start_time < 300:
                    time.sleep(10)
                    elapsed = int(time.time() - start_time)
                    log_callback(f"⏳ Polling task status... ({elapsed}s elapsed)")
                    res_poll = requests.get(polling_url, headers=headers, timeout=15)
                    if res_poll.status_code != 200:
                        continue
                        
                    status_data = res_poll.json()
                    status = status_data.get("status")
                    
                    if status == "completed":
                        log_callback("✅ Task completed! Downloading video file...")
                        content_url = f"https://openrouter.ai/api/v1/videos/{job_id}/content"
                        download_url = status_data.get("content_url") or content_url
                        
                        dl_res = requests.get(download_url, headers=headers, timeout=60)
                        if dl_res.status_code == 200:
                            output_path.parent.mkdir(parents=True, exist_ok=True)
                            output_path.write_bytes(dl_res.content)
                            log_callback(f"✅ Success! Saved to `{output_path.name}` ({dur}s @ {res}).")
                            return True
                        else:
                            dl_res2 = requests.get(content_url, headers=headers, timeout=60)
                            if dl_res2.status_code == 200:
                                output_path.parent.mkdir(parents=True, exist_ok=True)
                                output_path.write_bytes(dl_res2.content)
                                log_callback(f"✅ Success! Saved to `{output_path.name}` ({dur}s @ {res}).")
                                return True
                            log_callback(f"⚠️ Failed to download video content from URL: {content_url}")
                            break
                    elif status == "failed":
                        log_callback("⚠️ MiniMax video generation task failed on OpenRouter.")
                        break
                
                log_callback(f"⚠️ Config {dur}s @ {res} failed or timed out.")
            except Exception as e:
                log_callback(f"⚠️ Error during MiniMax config ({dur}s @ {res}): {e}")
                continue
                
        if key_failed:
            continue

    return False

# --- COMBINED GENERATOR DISPATCHER ---
def generate_single_video_clip_with_options(prompt: str, duration: int, output_path: Path, generator_type: str, log_callback) -> bool:
    if generator_type == "Google Veo (Gemini)":
        return generate_google_veo_clip(prompt, duration, output_path, log_callback)
    elif generator_type == "MiniMax M3 (OpenRouter)":
        return generate_minimax_video_clip(prompt, duration, output_path, log_callback)
    else:
        log_callback("⏳ Generator set to Auto-Fallback. Attempting Google Veo first...")
        success = generate_google_veo_clip(prompt, duration, output_path, log_callback)
        if success:
            return True
        log_callback("⚠️ Google Veo failed. Falling back to MiniMax M3 via OpenRouter...")
        return generate_minimax_video_clip(prompt, duration, output_path, log_callback)

# --- FFmpeg STITCHING ENGINE ---
def compile_master_video(video_files: dict, output_dir: Path) -> Path | None:
    sorted_keys = sorted(video_files.keys(), key=lambda x: int(x.split("_")[1]))
    valid_files = []
    for k in sorted_keys:
        path_str = video_files[k]
        if path_str and Path(path_str).exists():
            valid_files.append(Path(path_str))
            
    if not valid_files:
        return None
        
    list_file = output_dir / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for path in valid_files:
            f.write(f"file '{path.absolute()}'\n")
            
    output_video = output_dir / "final_master_3d.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file.absolute()),
        "-c", "copy",
        str(output_video.absolute())
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if list_file.exists():
            list_file.unlink()
        return output_video
    except Exception as e:
        st.error(f"FFmpeg concatenation failed: {e}")
        if list_file.exists():
            list_file.unlink()
        return None

# --- AUTO-SCAN VIDEO FOLDER ---
def scan_existing_video_files(settings: Settings):
    """Scan disk folder to recover already generated clip files across page reloads."""
    proj_name = (st.session_state.get("video_studio_subject") or "3d_animation_project").strip()
    safe_proj_name = "".join([c if c.isalnum() or c in ("_", "-") else "_" for c in proj_name])
    output_folder = Path(settings.output_dir) / "video_episodes" / safe_proj_name / "3d_clips"
    
    if output_folder.exists():
        for file in output_folder.iterdir():
            if file.is_file() and file.name.startswith("scene_") and file.name.endswith(".mp4") and file.stat().st_size > 0:
                try:
                    num = int(file.name.split("_")[1].split(".")[0])
                    video_key = f"scene_{num}"
                    if video_key not in st.session_state["three_d_video_files"]:
                        st.session_state["three_d_video_files"][video_key] = str(file)
                except Exception:
                    pass

# --- STORYBOARDING AGENT SYSTEM PROMPT ---
STORYBOARD_SYSTEM_PROMPT = """You are an expert 3D animation director and visual storyboard planner.
Given a user's story and a calculated number of scenes (each lasting exactly 8 seconds), split the story chronologically.

Most importantly, you MUST ensure all scenes are highly interconnected with absolute character and visual consistency:
1. CHARACTER CONSISTENCY IS CRITICAL: Identify the main character (and key sub-characters). You must establish a detailed, specific, and unchanging visual signature for them (e.g., specific age, brown curly hair, bright yellow shirt with a red star on it, blue denim shorts, white sneakers, large expressive blue eyes). You MUST repeat this exact character description in EVERY single video prompt. Do not just say "the boy" or "the character"; write the full description each time so the generator does not change their appearance.
2. VISUAL STYLE CONTINUITY: Keep the exact same style modifiers in every prompt (e.g., "3D Pixar claymation style, high-end clay textures, vibrant warm lighting, clean detailed environment, octane render, 8k resolution").
3. CAMERA FLOW & MOVEMENT: Detail camera angles and movements (e.g., "slow panning shot", "tracking camera following the character", "medium close-up, camera dollying out") that transition smoothly from one scene to the next.
4. ACTION FLOW: The ending action of Scene N must flow logically into the starting action of Scene N+1. For example, if scene 1 ends with the character running to a door, scene 2 must start with the character opening that same door and stepping inside.

Format your response as a valid JSON array of objects. Do not include any explanations, code blocks, or preamble. Just raw JSON.
Each object must have the keys:
- "scene_number": (integer starting from 1)
- "narrative": (string) Story portion for this segment.
- "video_prompt": (string) Rich, detailed 3D video generation prompt specifying the exact character description, action, camera movement, and consistent Pixar claymation style.
- "transition_hint": (string) Visual flow description from previous scene.
"""

# --- STREAMLIT UI RENDERER ---
def render_3d_video_studio(settings: Settings) -> None:
    st.markdown(
        """
        <div class="hero" style="background: linear-gradient(135deg, rgba(56,189,248,0.15), rgba(99,102,241,0.15)); border: 1px solid rgba(56,189,248,0.3); margin-bottom: 24px;">
          <h1 style="font-size: 32px;">🔮 3D Video Studio (Google Veo Director)</h1>
          <p style="margin-top: 6px; font-size: 14px;">Co-create continuous 8-second 3D cartoon scenes with your AI Director agent. Ensure cinematic consistency and fluid transitions.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Initialize states
    if "three_d_messages" not in st.session_state:
        st.session_state["three_d_messages"] = [
            {"role": "assistant", "content": "Hello! I am your 3D animation director. Tell me about the story you want to create and how long it should be. I'll split it into perfectly interconnected 8-second scenes and write prompts to generate them!"}
        ]
    if "three_d_scenes" not in st.session_state:
        st.session_state["three_d_scenes"] = []
    if "three_d_video_files" not in st.session_state:
        st.session_state["three_d_video_files"] = {}
    if "three_d_generating" not in st.session_state:
        st.session_state["three_d_generating"] = False
    if "three_d_master_video" not in st.session_state:
        st.session_state["three_d_master_video"] = ""
    if "three_d_generation_logs" not in st.session_state:
        st.session_state["three_d_generation_logs"] = []

    # Automatically scan for existing generated clips
    scan_existing_video_files(settings)

    col_chat, col_storyboard = st.columns([4.5, 5.5])

    # Left Column: Chat Agent Interaction
    with col_chat:
        st.subheader("💬 AI Director Chat")
        
        # Render Chat Container
        chat_container = st.container(height=380)
        for msg in st.session_state["three_d_messages"]:
            if msg["role"] == "assistant":
                chat_container.chat_message("assistant", avatar="🔮").write(msg["content"])
            else:
                chat_container.chat_message("user").write(msg["content"])

        # Input variables below chat
        with st.form("three_d_inputs_form", clear_on_submit=False):
            user_story = st.text_area("Your Story / Concept", placeholder="Write your story here...", height=100)
            project_name = st.text_input("Project Folder Name", value="3d_animation_project", key="video_studio_subject")
            story_length = st.number_input("Desired Story Length (seconds)", min_value=8, max_value=300, value=24, step=8)
            num_scenes = int(story_length // 8)
            
            chat_input = st.text_input("Refinement Instructions (Optional)", placeholder="e.g. 'Make the main character a green baby dragon'")
            
            submit_btn = st.form_submit_button("🚀 Brainstorm Storyboard", use_container_width=True)

        if submit_btn:
            if not user_story.strip():
                st.error("Please provide a story concept to start!")
            else:
                user_msg_content = f"Story: {user_story}\nLength: {story_length}s ({num_scenes} scenes)\nRefinements: {chat_input}"
                st.session_state["three_d_messages"].append({"role": "user", "content": user_msg_content})
                
                with st.spinner("AI Director is designing the storyboard..."):
                    llm_prompt = f"{STORYBOARD_SYSTEM_PROMPT}\n\nUser Story: {user_story}\nNumber of Scenes: {num_scenes}\nExtra Directives: {chat_input}"
                    try:
                        # Estimate output tokens dynamically. Each scene is ~250 tokens.
                        estimated_tokens = min(8192, max(2000, num_scenes * 250))
                        llm_response = call_prompt_llm(settings, llm_prompt, max_tokens=estimated_tokens)
                        if not llm_response:
                            raise ValueError("AI Director returned an empty or invalid storyboard response. Please check your API keys or try again.")
                        cleaned_resp = llm_response.strip()
                        
                        # Clean JSON code fence
                        if "```json" in cleaned_resp:
                            cleaned_resp = cleaned_resp.split("```json")[1].split("```")[0].strip()
                        elif "```" in cleaned_resp:
                            cleaned_resp = cleaned_resp.split("```")[1].split("```")[0].strip()
                            
                        # Use our robust json repair tool to handle truncations gracefully
                        parsed_scenes = repair_truncated_json_array(cleaned_resp)
                        st.session_state["three_d_scenes"] = parsed_scenes
                        
                        # Clear old generated video files from session state and disk on new brainstorm
                        st.session_state["three_d_video_files"] = {}
                        st.session_state["three_d_master_video"] = ""
                        st.session_state["three_d_generation_error"] = ""
                        st.session_state["three_d_generation_logs"] = []
                        
                        proj_name = (st.session_state.get("video_studio_subject") or "3d_animation_project").strip()
                        safe_proj_name = "".join([c if c.isalnum() or c in ("_", "-") else "_" for c in proj_name])
                        
                        # Remove individual scene clips using robust delete
                        output_folder = Path(settings.output_dir) / "video_episodes" / safe_proj_name / "3d_clips"
                        robust_delete_folder(output_folder)
                                
                        # Remove compiled master video
                        master_path = Path(settings.output_dir) / "video_episodes" / safe_proj_name / "final_master_3d.mp4"
                        if master_path.exists():
                            try:
                                master_path.unlink()
                            except Exception:
                                pass
                        
                        num_recovered = len(parsed_scenes)
                        if num_recovered < num_scenes:
                            agent_reply = f"I generated the storyboard for your concept. Due to length limits, I parsed {num_recovered} out of {num_scenes} scenes successfully. Please review and refine the storyboard on the right!"
                        else:
                            agent_reply = f"Excellent! I've broken down your story into {num_scenes} interconnected 8-second scenes. I designed the video prompts to maintain strong visual continuity (same style, camera moves, and character details). Please review and refine the storyboard on the right!"
                            
                        st.session_state["three_d_messages"].append({"role": "assistant", "content": agent_reply})
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error during storyboard generation: {e}")

    # Right Column: Storyboard Editor & Compilation
    with col_storyboard:
        st.subheader("📋 Storyboard Scene Editor")
        
        # Display generation error if present
        if st.session_state.get("three_d_generation_error"):
            st.error(st.session_state["three_d_generation_error"])
            
        # Display past generation logs if present
        if st.session_state.get("three_d_generation_logs") and not st.session_state["three_d_generating"]:
            with st.expander("📝 Show Last Generation Logs", expanded=False):
                st.code("\n".join(st.session_state["three_d_generation_logs"]))
                
        # Generator provider selection
        generator_choice = st.selectbox(
            "Select 3D Video Generator Provider",
            options=["Auto-Fallback", "Google Veo (Gemini)", "MiniMax M3 (OpenRouter)"],
            key="three_d_generator_selection"
        )
        
        # Placeholder for active video generation progress (will render at the top when generating)
        progress_placeholder = st.empty()
        
        if not st.session_state["three_d_scenes"]:
            st.info("Your storyboard scenes will appear here once you brainstorm with the Director agent on the left.")
        else:
            edited_scenes = []
            for idx, scene in enumerate(st.session_state["three_d_scenes"]):
                with st.expander(f"🎬 Scene {scene.get('scene_number', idx+1)}: {scene.get('transition_hint', 'Transition')[:40]}...", expanded=True):
                    scene_num = scene.get('scene_number', idx+1)
                    narrative = st.text_area(f"Narrative Chunk (Scene {scene_num})", value=scene.get('narrative', ''), key=f"narrative_{idx}", height=60)
                    prompt_text = st.text_area(f"Video Prompt (Scene {scene_num})", value=scene.get('video_prompt', ''), key=f"prompt_{idx}", height=100)
                    
                    # Preview Box
                    video_key = f"scene_{scene_num}"
                    video_path_str = st.session_state["three_d_video_files"].get(video_key)
                    if video_path_str and Path(video_path_str).exists():
                        st.video(video_path_str)
                    
                    edited_scenes.append({
                        "scene_number": scene_num,
                        "narrative": narrative,
                        "video_prompt": prompt_text,
                        "transition_hint": scene.get('transition_hint', '')
                    })
            
            # Save edits
            st.session_state["three_d_scenes"] = edited_scenes
            
            st.markdown("---")
            
            # Compilation Trigger Button
            if not st.session_state["three_d_generating"]:
                if st.button("🎬 Generate All 3D Video Clips (1-by-1 with preview)", type="primary", use_container_width=True):
                    st.session_state["three_d_generating"] = True
                    st.session_state["three_d_generation_error"] = ""
                    st.session_state["three_d_generation_logs"] = [] # Clear old logs
                    st.rerun()
            else:
                if st.button("🛑 Stop Generation", type="secondary", use_container_width=True):
                    st.session_state["three_d_generating"] = False
                    st.rerun()

        # Stitching / Compilation of Final Master Video
        st.markdown("---")
        st.subheader("🏆 Stitch & Render Final Video")
        st.caption("Stitch all successfully generated scene clips together using FFmpeg codec copy (lossless concat).")
        
        proj_name = (st.session_state.get("video_studio_subject") or "3d_animation_project").strip()
        safe_proj_name = "".join([c if c.isalnum() or c in ("_", "-") else "_" for c in proj_name])
        output_folder = Path(settings.output_dir) / "video_episodes" / safe_proj_name
        master_video_path = output_folder / "final_master_3d.mp4"
        
        # Enable button only if we have generated files
        has_files = len(st.session_state.get("three_d_video_files", {})) > 0
        
        if not has_files:
            st.info("💡 Once you generate at least one scene video, the button below will activate to let you compile the final movie!")
        
        if st.button("🎬 Compile Final Master Video", type="primary", use_container_width=True, disabled=not has_files, key="btn_compile_master_root"):
            with st.spinner("Stitching clips..."):
                compiled_path = compile_master_video(st.session_state["three_d_video_files"], output_folder)
                if compiled_path and compiled_path.exists():
                    st.session_state["three_d_master_video"] = str(compiled_path)
                    st.toast("Final Master Video compiled successfully!")
                    st.rerun()
        
        if master_video_path.exists():
            st.session_state["three_d_master_video"] = str(master_video_path)
            st.video(str(master_video_path))
            st.success(f"Location: `{master_video_path}`")

    # --- ACTIVE GENERATION LOOP CONTROL & PROGRESS LOGS DISPLAY ---
    if st.session_state["three_d_generating"]:
        next_scene = None
        total_scenes = len(st.session_state["three_d_scenes"])
        completed_count = 0
        for scene in st.session_state["three_d_scenes"]:
            scene_num = int(scene["scene_number"])
            video_key = f"scene_{scene_num}"
            video_path_str = st.session_state["three_d_video_files"].get(video_key)
            if video_path_str and Path(video_path_str).exists() and Path(video_path_str).stat().st_size > 0:
                completed_count += 1
            elif next_scene is None:
                next_scene = scene

        if next_scene:
            scene_num = int(next_scene["scene_number"])
            
            proj_name = (st.session_state.get("video_studio_subject") or "3d_animation_project").strip()
            safe_proj_name = "".join([c if c.isalnum() or c in ("_", "-") else "_" for c in proj_name])
            output_folder = Path(settings.output_dir) / "video_episodes" / safe_proj_name / "3d_clips"
            output_folder.mkdir(parents=True, exist_ok=True)
            output_path = output_folder / f"scene_{scene_num:02d}.mp4"
            
            # Setup logging container in UI using the placeholder defined at the top
            def local_logger(msg: str):
                st.session_state["three_d_generation_logs"].append(msg)
                with progress_placeholder.container():
                    st.markdown(
                        f"""
                        <div style="background: linear-gradient(135deg, rgba(56,189,248,0.1), rgba(99,102,241,0.1)); border: 1px solid rgba(56,189,248,0.4); border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                          <h4 style="margin: 0; color: #38bdf8; font-size: 16px; display: flex; align-items: center; gap: 8px;">
                            ⚡ Active 3D Video Generation: Scene {scene_num} of {total_scenes}
                          </h4>
                          <p style="margin: 4px 0 12px 0; font-size: 13px; color: #94a3b8;">
                            Generating sequentially using provider: <strong>{generator_choice}</strong>. Please keep this tab active.
                          </p>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    # Overall progress bar
                    progress_ratio = completed_count / total_scenes if total_scenes > 0 else 0.0
                    st.progress(progress_ratio, text=f"Overall completion: {completed_count}/{total_scenes} scene clips ready ({int(progress_ratio*100)}%)")
                    
                    # Collapsible expander for live polling logs (stable and avoids DuplicateWidgetID)
                    with st.expander(f"⏳ Generation Status: {msg}", expanded=True):
                        st.code("\n".join(st.session_state["three_d_generation_logs"]))
                    
                    st.markdown("---")
            
            local_logger(f"🚀 Starting generation for Scene {scene_num}...")
            
            success = generate_single_video_clip_with_options(
                prompt=next_scene["video_prompt"],
                duration=8,
                output_path=output_path,
                generator_type=generator_choice,
                log_callback=local_logger
            )
            
            if success:
                st.session_state["three_d_video_files"][f"scene_{scene_num}"] = str(output_path)
                local_logger(f"✅ Scene {scene_num} generation complete!")
                time.sleep(1)
            else:
                st.session_state["three_d_generation_error"] = f"❌ Generation failed at Scene {scene_num}. Please check logs below."
                st.session_state["three_d_generating"] = False
                st.rerun()
            
            st.rerun()
        else:
            st.session_state["three_d_generating"] = False
            st.toast("🏆 Storyboard video compilation completed successfully!")
            st.rerun()
