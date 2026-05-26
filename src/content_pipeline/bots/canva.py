"""Canva Connect API adapter for brand-template autofill and MP4 export.

Provides an optional video-rendering path that uses a Canva brand template
with text fields (headline, hook, point_1..point_3, cta) to generate a
designed video, then exports it as MP4 and downloads the result.

Usage (from the pipeline)::

    if settings.canva_client_id and settings.canva_brand_template_id:
        canva_path = render_canva_video(package, settings, storage)
"""

from __future__ import annotations

import base64
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage

log = logging.getLogger(__name__)

CANVA_API_BASE = "https://api.canva.com/rest/v1"
TOKEN_URL = f"{CANVA_API_BASE}/oauth/token"
DEFAULT_POLL_INTERVAL = 2  # seconds
MAX_POLL_ATTEMPTS = 60  # ~2 minutes max


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

class CanvaAuth:
    """Stores a refresh token and transparently refreshes access tokens."""

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.canva_client_id
        self._client_secret = settings.canva_client_secret
        self._refresh_token = settings.canva_refresh_token
        self._dotenv_path = settings.dotenv_path
        self._access_token: str | None = None
        self._expires_at: float = 0

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing the current one if needed."""
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        return self._refresh()

    def _refresh(self) -> str:
        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        resp = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]
        if "refresh_token" in data:
            self._refresh_token = data["refresh_token"]
            self._persist_refresh_token()
        return self._access_token

    def _persist_refresh_token(self) -> None:
        """Save Canva's rotated single-use refresh token for the next run."""
        os.environ["CANVA_REFRESH_TOKEN"] = self._refresh_token
        if self._dotenv_path is None:
            log.warning(
                "Canva issued a replacement refresh token, but no .env path is configured."
            )
            return

        content = (
            self._dotenv_path.read_text(encoding="utf-8")
            if self._dotenv_path.exists()
            else ""
        )
        entry = f"CANVA_REFRESH_TOKEN={self._refresh_token}"
        updated, replacements = re.subn(
            r"^CANVA_REFRESH_TOKEN=.*$",
            entry,
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if replacements == 0:
            separator = "" if not content or content.endswith("\n") else "\n"
            updated = f"{content}{separator}{entry}\n"

        temporary_path = self._dotenv_path.with_suffix(
            f"{self._dotenv_path.suffix}.tmp"
        )
        temporary_path.write_text(updated, encoding="utf-8")
        temporary_path.replace(self._dotenv_path)


# ---------------------------------------------------------------------------
# Brand template helpers
# ---------------------------------------------------------------------------

def get_brand_template_dataset(
    auth: CanvaAuth, template_id: str
) -> dict[str, str]:
    """Return ``{field_name: field_type}`` for the brand template."""
    token = auth.get_access_token()
    resp = requests.get(
        f"{CANVA_API_BASE}/brand-templates/{template_id}/dataset",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json().get("dataset", {})
    return {name: meta["type"] for name, meta in raw.items()}


# ---------------------------------------------------------------------------
# Autofill
# ---------------------------------------------------------------------------

def create_autofill_job(
    auth: CanvaAuth, template_id: str, field_values: dict[str, str]
) -> str:
    """Submit an autofill job and return the job ID.

    *field_values* maps field names (as created in the Canva template) to
    the text to insert.
    """
    token = auth.get_access_token()
    payload: dict[str, Any] = {
        "brand_template_id": template_id,
        "data": {},
    }
    for field_name, text in field_values.items():
        payload["data"][field_name] = {"type": "text", "text": text}

    resp = requests.post(
        f"{CANVA_API_BASE}/autofills",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["job"]["id"]


def _extract_design_id(design_url: str) -> str:
    """Extract the design ID from a Canva edit URL.

    Expected format:  https://www.canva.com/design/{DESIGN-ID}/edit
    """
    m = re.search(r"/design/([^/]+)", design_url)
    if not m:
        raise ValueError(f"Could not extract design ID from URL: {design_url}")
    return m.group(1)


def poll_autofill_job(
    auth: CanvaAuth,
    job_id: str,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_attempts: int = MAX_POLL_ATTEMPTS,
) -> str:
    """Poll the autofill job until it completes and return the **design URL**."""
    token = auth.get_access_token()
    for _ in range(max_attempts):
        resp = requests.get(
            f"{CANVA_API_BASE}/autofills/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        job = resp.json()["job"]
        status = job["status"]
        if status == "success":
            return job["result"]["design"]["url"]
        if status == "failed":
            raise RuntimeError(
                f"Autofill job {job_id} failed: {job.get('error', job)}"
            )
        time.sleep(poll_interval)
    raise TimeoutError(f"Autofill job {job_id} did not complete in time")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def create_export_job(auth: CanvaAuth, design_id: str) -> str:
    """Start an MP4 export and return the export job ID."""
    token = auth.get_access_token()
    resp = requests.post(
        f"{CANVA_API_BASE}/exports",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "design_id": design_id,
            "format": {"type": "mp4"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["job"]["id"]


def poll_export_job(
    auth: CanvaAuth,
    job_id: str,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_attempts: int = MAX_POLL_ATTEMPTS,
) -> list[str]:
    """Poll the export job and return the list of download URLs."""
    token = auth.get_access_token()
    for _ in range(max_attempts):
        resp = requests.get(
            f"{CANVA_API_BASE}/exports/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        job = resp.json()["job"]
        status = job["status"]
        if status == "success":
            return job.get("urls", [])
        if status == "failed":
            raise RuntimeError(
                f"Export job {job_id} failed: {job.get('error', job)}"
            )
        time.sleep(poll_interval)
    raise TimeoutError(f"Export job {job_id} did not complete in time")


def download_export(url: str, output_path: Path) -> Path:
    """Download a file from a Canva export URL to *output_path*."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


# ---------------------------------------------------------------------------
# High-level pipeline entry point
# ---------------------------------------------------------------------------

FIELD_MAP = (
    ("headline", "topic"),
    ("hook", "video_script.hook"),
    ("point_1", "video_script.points[0]"),
    ("point_2", "video_script.points[1]"),
    ("point_3", "video_script.points[2]"),
    ("cta", "video_script.cta"),
)


def _resolve_field(package: ContentPackage, dotted: str) -> str:
    """Resolve a dotted member path on a ContentPackage into a string."""
    # Simple attribute access only – no eval.
    value: Any = package
    for part in dotted.replace("]", "").split("."):
        if "[" in part:
            attr, idx = part.split("[", 1)
            value = getattr(value, attr)[int(idx)]
        else:
            value = getattr(value, part)
    return str(value).strip()


def render_canva_video(
    package: ContentPackage,
    settings: Settings,
    storage: LocalDailyStorage,
) -> str:
    """Render a video via Canva Autofill + Export.

    Requires *settings.canva_brand_template_id* to be set together with
    valid Canva OAuth credentials (``canva_client_id``, ``canva_client_secret``,
    ``canva_refresh_token``).

    Returns a relative path (e.g. ``video/canva_export.mp4``) suitable for
    inclusion in the pipeline manifest.
    """
    template_id = settings.canva_brand_template_id
    if not template_id:
        raise ValueError(
            "CANVA_BRAND_TEMPLATE_ID is not set. "
            "Publish a brand template in Canva and add its ID to .env."
        )

    auth = CanvaAuth(settings)

    # 1. (Optional) Verify the template is reachable.
    dataset = get_brand_template_dataset(auth, template_id)
    log.info("Canva template %s dataset: %s", template_id, dataset)

    # 2. Build field values from the content package.
    field_values: dict[str, str] = {}
    for canva_field, package_path in FIELD_MAP:
        if dataset.get(canva_field) != "text":
            log.warning(
                "Skipping Canva field %s: no matching text autofill field in template",
                canva_field,
            )
            continue
        try:
            field_values[canva_field] = _resolve_field(package, package_path)
        except (AttributeError, IndexError, ValueError) as exc:
            log.warning("Skipping Canva field %s: %s", canva_field, exc)

    if not field_values:
        expected_fields = ", ".join(name for name, _ in FIELD_MAP)
        raise ValueError(
            "Canva brand template has none of the expected text autofill fields: "
            f"{expected_fields}. Add them with Canva Data Autofill and republish "
            "the brand template."
        )

    log.info(
        "Starting Canva autofill for template %s with fields: %s",
        template_id,
        list(field_values),
    )

    # 3. Autofill.
    autofill_job_id = create_autofill_job(auth, template_id, field_values)
    design_url = poll_autofill_job(auth, autofill_job_id)
    design_id = _extract_design_id(design_url)
    log.info("Autofill complete – design ID: %s", design_id)

    # 4. Export as MP4.
    export_job_id = create_export_job(auth, design_id)
    download_urls = poll_export_job(auth, export_job_id)
    if not download_urls:
        raise RuntimeError("Export succeeded but no download URLs were returned.")
    log.info("Export complete – %d file(s) available", len(download_urls))

    # 5. Download first (and usually only) URL.
    output_rel = "video/canva_export.mp4"
    output_path = storage.daily_path(package.date, output_rel)
    download_export(download_urls[0], output_path)
    log.info("Canva video saved to %s", output_path)

    return output_rel
