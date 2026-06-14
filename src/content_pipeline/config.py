from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    output_dir: Path
    mode: str = "mock"
    prompt_provider: str = "mock"
    image_provider: str = "gemini"
    openai_api_key: str = ""
    openai_api_keys: tuple[str, ...] = ()
    openai_model: str = "gpt-5.4-mini"
    openai_image_model: str = "gpt-image-1"
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    claude_code_use_bedrock: bool = False
    claude_bedrock_model_id: str = ""
    bedrock_model_id: str = "global.amazon.nova-2-lite-v1:0"
    bedrock_auth_mode: str = "iam"
    aws_region: str = "ap-southeast-2"
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    imagen_model: str = "imagen-4.0-generate-001"
    gemini_image_model: str = "gemini-2.5-flash-image"
    gemini_image_daily_budget: int = 90
    gemini_image_min_interval_seconds: float = 30.0
    gemini_image_max_attempts: int = 8
    gemini_image_retry_backoff_seconds: float = 120.0
    image_request_delay_seconds: float = 0.0
    image_fallback_provider: str = "pollinations"
    voice_provider: str = "edge"
    indian_tts_voice: str = "en-IN-PrabhatNeural"
    voicebox_url: str = "http://127.0.0.1:17493"
    image_max_dimension: int = 4096
    image_max_bytes: int = 5 * 1024 * 1024
    publish_linkedin: bool = False
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8080/callback"
    linkedin_access_token: str = ""
    linkedin_member_urn: str = ""
    canva_client_id: str = ""
    canva_client_secret: str = ""
    canva_redirect_uri: str = "http://127.0.0.1:8080/callback"
    canva_refresh_token: str = ""
    canva_brand_template_id: str = ""
    motion_provider: str = "openai_sora"
    motion_model: str = "sora-2"
    luma_api_key: str = ""
    luma_image_model: str = "photon-1"
    luma_video_model: str = "ray-2"
    reference_audio_dir: Path | None = None
    hf_token: str = ""
    hf_tokens: tuple[str, ...] = ()
    hf_token_keys: tuple[str, ...] = ()
    hf_song_generation_space: str = ""
    hf_video_render_mode: str = "zero_gpu_space"
    hf_zero_gpu_space_id: str = ""
    hf_zero_gpu_space_api_name: str = "/render_package"
    hf_zero_gpu_video_model: str = "stabilityai/stable-video-diffusion-img2vid-xt-1-1"
    hf_zero_gpu_space_timeout_seconds: int = 1800
    hf_video_model: str = "Wan-AI/Wan2.2-I2V-A14B"
    hf_video_provider: str = "auto"
    gemini_api_key: str = ""
    gemini_api_keys: tuple[str, ...] = ()
    gemini_video_model: str = "veo-3.0-fast-generate-001"
    gemini_video_poll_seconds: int = 10
    gemini_video_price_per_second_usd: float = 0.15
    gemini_video_daily_clip_budget: int = 3
    gemini_video_monthly_budget_usd: float = 25.0
    youtube_client_secrets_file: str = ""
    youtube_token_file: str = ""
    youtube_channel_url: str = ""
    instagram_access_token: str = ""
    instagram_user_id: str = ""
    instagram_client_id: str = ""
    instagram_client_secret: str = ""
    nvidia_api_key: str = ""
    nvidia_api_keys: tuple[str, ...] = ()
    nvidia_image_model: str = "qwen/qwen-image"
    nvidia_nim_model: str = "microsoft/phi-4-mini-instruct"
    together_api_key: str = ""
    together_api_keys: tuple[str, ...] = ()
    pollinations_api_key: str = ""
    local_llm_url: str = "http://localhost:11434/v1"
    local_llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    comic_voice_model_repo: str = "ai4bharat/indic-parler-tts"
    comic_kokoro_model_repo: str = "hexgrad/Kokoro-82M"
    comic_chatterbox_model_repo: str = "ResembleAI/chatterbox"
    dotenv_path: Path | None = None

    @classmethod
    def from_environment(cls, project_dir: Path | None = None) -> "Settings":
        project_dir = project_dir or Path.cwd()
        _load_dotenv(project_dir / ".env")
        output_dir = Path(os.getenv("CONTENT_OUTPUT_DIR", "output"))
        if not output_dir.is_absolute():
            output_dir = project_dir / output_dir
        return cls(
            output_dir=output_dir,
            mode=os.getenv("PIPELINE_MODE", "mock").strip().lower(),
            prompt_provider=os.getenv("PROMPT_PROVIDER", "mock").strip().lower(),
            image_provider=os.getenv("IMAGE_PROVIDER", "gemini").strip().lower(),
            openai_api_keys=(_openai_keys := _read_key_pool("OPENAI_API_KEY", 5)),
            openai_api_key=_first_key(_openai_keys, os.getenv("OPENAI_API_KEY", "")),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", ""),
            claude_code_use_bedrock=_as_bool(os.getenv("CLAUDE_CODE_USE_BEDROCK", "false")),
            claude_bedrock_model_id=os.getenv("CLAUDE_BEDROCK_MODEL_ID", "").strip(),
            bedrock_model_id=os.getenv(
                "BEDROCK_MODEL_ID",
                "global.amazon.nova-2-lite-v1:0",
            ).strip(),
            bedrock_auth_mode=os.getenv("BEDROCK_AUTH_MODE", "iam").strip().lower(),
            aws_region=(
                os.getenv("AWS_REGION", "")
                or os.getenv("AWS_DEFAULT_REGION", "")
                or "ap-southeast-2"
            ).strip(),
            gcp_project_id=os.getenv("GCP_PROJECT_ID", ""),
            gcp_location=os.getenv("GCP_LOCATION", "us-central1"),
            imagen_model=os.getenv("IMAGEN_MODEL", "imagen-4.0-generate-001"),
            gemini_image_model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
            gemini_image_daily_budget=int(os.getenv("GEMINI_IMAGE_DAILY_BUDGET", "90")),
            gemini_image_min_interval_seconds=float(
                os.getenv("GEMINI_IMAGE_MIN_INTERVAL_SECONDS", "30")
            ),
            gemini_image_max_attempts=int(os.getenv("GEMINI_IMAGE_MAX_ATTEMPTS", "8")),
            gemini_image_retry_backoff_seconds=float(
                os.getenv("GEMINI_IMAGE_RETRY_BACKOFF_SECONDS", "120")
            ),
            image_request_delay_seconds=float(os.getenv("IMAGE_REQUEST_DELAY_SECONDS", "0.0")),
            image_fallback_provider=os.getenv("IMAGE_FALLBACK_PROVIDER", "pollinations").strip().lower(),
            voice_provider="edge",
            indian_tts_voice=os.getenv("INDIAN_TTS_VOICE", "en-IN-PrabhatNeural"),
            voicebox_url=os.getenv(
                "VOICEBOX_URL",
                "http://127.0.0.1:17493",
            ).strip().rstrip("/"),
            image_max_dimension=int(os.getenv("IMAGE_MAX_DIMENSION", "4096")),
            image_max_bytes=int(os.getenv("IMAGE_MAX_BYTES", str(5 * 1024 * 1024))),
            publish_linkedin=_as_bool(os.getenv("PUBLISH_LINKEDIN", "false")),
            linkedin_client_id=os.getenv("LINKEDIN_CLIENT_ID", ""),
            linkedin_client_secret=os.getenv("LINKEDIN_CLIENT_SECRET", ""),
            linkedin_redirect_uri=os.getenv(
                "LINKEDIN_REDIRECT_URI", "http://localhost:8080/callback"
            ),
            linkedin_access_token=os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
            linkedin_member_urn=os.getenv("LINKEDIN_MEMBER_URN", ""),
            canva_client_id=os.getenv("CANVA_CLIENT_ID", ""),
            canva_client_secret=os.getenv("CANVA_CLIENT_SECRET", ""),
            canva_redirect_uri=os.getenv(
                "CANVA_REDIRECT_URI", "http://127.0.0.1:8080/callback"
            ),
            canva_refresh_token=os.getenv("CANVA_REFRESH_TOKEN", ""),
            canva_brand_template_id=os.getenv("CANVA_BRAND_TEMPLATE_ID", ""),
            motion_provider=os.getenv("MOTION_PROVIDER", "openai_sora").strip().lower(),
            motion_model=os.getenv("MOTION_MODEL", "sora-2"),
            luma_api_key=os.getenv("LUMAAI_API_KEY", ""),
            luma_image_model=os.getenv("LUMA_IMAGE_MODEL", "photon-1"),
            luma_video_model=os.getenv("LUMA_VIDEO_MODEL", "ray-2"),
            reference_audio_dir=(
                Path(ref_audio_dir)
                if (ref_audio_dir := os.getenv("REFERENCE_AUDIO_DIR", "").strip())
                else None
            ),
            hf_tokens=(_hf_tokens := _read_key_pool("HF_TOKEN", 10, fallback_env="HF_API_KEY")),
            hf_token_keys=_hf_tokens,
            hf_token=_first_key(
                _hf_tokens,
                os.getenv("HF_TOKEN", "") or os.getenv("HF_API_KEY", ""),
            ),
            hf_song_generation_space=os.getenv("HF_SONG_GENERATION_SPACE", "").strip(),
            hf_video_render_mode=os.getenv("HF_VIDEO_RENDER_MODE", "zero_gpu_space").strip().lower() or "zero_gpu_space",
            hf_zero_gpu_space_id=os.getenv("HF_ZERO_GPU_SPACE_ID", "").strip(),
            hf_zero_gpu_space_api_name=os.getenv("HF_ZERO_GPU_SPACE_API_NAME", "/render_package").strip() or "/render_package",
            hf_zero_gpu_video_model=os.getenv(
                "HF_ZERO_GPU_VIDEO_MODEL",
                "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
            ).strip(),
            hf_zero_gpu_space_timeout_seconds=int(os.getenv("HF_ZERO_GPU_SPACE_TIMEOUT_SECONDS", "1800")),
            hf_video_model=os.getenv("HF_VIDEO_MODEL", "Wan-AI/Wan2.2-I2V-A14B").strip(),
            hf_video_provider=os.getenv("HF_VIDEO_PROVIDER", "auto").strip().lower() or "auto",
            gemini_api_keys=(_gemini_keys := _read_key_pool("GEMINI_API_KEY", 10, fallback_env="GOOGLE_API_KEY")),
            gemini_api_key=_first_key(
                _gemini_keys,
                os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", ""),
            ),
            gemini_video_model=os.getenv("GEMINI_VIDEO_MODEL", "veo-3.0-fast-generate-001"),
            gemini_video_poll_seconds=int(os.getenv("GEMINI_VIDEO_POLL_SECONDS", "10")),
            gemini_video_price_per_second_usd=float(os.getenv("GEMINI_VIDEO_PRICE_PER_SECOND_USD", "0.15")),
            gemini_video_daily_clip_budget=int(os.getenv("GEMINI_VIDEO_DAILY_CLIP_BUDGET", "3")),
            gemini_video_monthly_budget_usd=float(os.getenv("GEMINI_VIDEO_MONTHLY_BUDGET_USD", "25.0")),
            youtube_client_secrets_file=os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", ""),
            youtube_token_file=os.getenv("YOUTUBE_TOKEN_FILE", ""),
            youtube_channel_url=os.getenv("YOUTUBE_CHANNEL_URL", ""),
            instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            instagram_user_id=os.getenv("INSTAGRAM_USER_ID", ""),
            instagram_client_id=os.getenv("INSTAGRAM_CLIENT_ID", ""),
            instagram_client_secret=os.getenv("INSTAGRAM_CLIENT_SECRET", ""),
            nvidia_api_keys=(
                _nvidia_keys := _read_key_pool(
                    "NVIDIA_API_KEY",
                    20,
                    fallback_env="NVIDIA_NIM_API_KEY",
                )
            ),
            nvidia_api_key=_first_key(
                _nvidia_keys,
                os.getenv("NVIDIA_API_KEY", "") or os.getenv("NVIDIA_NIM_API_KEY", ""),
            ),
            nvidia_image_model=os.getenv("NVIDIA_IMAGE_MODEL", "qwen/qwen-image"),
            nvidia_nim_model=os.getenv("NVIDIA_NIM_MODEL", "microsoft/phi-4-mini-instruct"),
            together_api_keys=(_together_keys := _read_key_pool("TOGETHER_API_KEY", 5)),
            together_api_key=_first_key(_together_keys, os.getenv("TOGETHER_API_KEY", "")),
            pollinations_api_key=os.getenv("POLLINATIONS_API_KEY", ""),
            local_llm_url=os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
            local_llm_model=os.getenv("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
            comic_voice_model_repo=os.getenv("COMIC_VOICE_MODEL_REPO", "ai4bharat/indic-parler-tts"),
            comic_kokoro_model_repo=os.getenv("COMIC_KOKORO_MODEL_REPO", "hexgrad/Kokoro-82M"),
            comic_chatterbox_model_repo=os.getenv("COMIC_CHATTERBOX_MODEL_REPO", "ResembleAI/chatterbox"),
            dotenv_path=project_dir / ".env",
        )


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned = _clean_env_value(value)
        os.environ.setdefault(key.strip(), cleaned)


def _clean_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return value
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    # Strip inline comments for unquoted values while preserving URLs or hashes inside quoted secrets.
    hash_index = value.find(" #")
    if hash_index != -1:
        value = value[:hash_index].rstrip()
    elif value.startswith("#"):
        value = ""
    return value


def _read_key_pool(prefix: str, total_slots: int, fallback_env: str | None = None) -> tuple[str, ...]:
    keys: list[str] = []
    primary = os.getenv(prefix, "").strip()
    if primary:
        keys.append(primary)
    for index in range(2, total_slots + 1):
        value = os.getenv(f"{prefix}_{index}", "").strip()
        if value:
            keys.append(value)
    if not keys and fallback_env:
        fallback = os.getenv(fallback_env, "").strip()
        if fallback:
            keys.append(fallback)
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def _first_key(pool: tuple[str, ...], fallback: str) -> str:
    if pool:
        return pool[0]
    return fallback
