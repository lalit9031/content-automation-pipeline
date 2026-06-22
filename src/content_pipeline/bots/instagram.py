"""Instagram Reels publishing via the Instagram Graph API.

Requirements
------------
- A Facebook Page connected to an Instagram Business (or Creator) Account.
- A long-lived Page Access Token with the ``instagram_basic`` and
  ``instagram_content_publish`` permissions.
- The Instagram Business Account ID (``ig-user-id``) obtained via
  ``/{facebook-page-id}?fields=instagram_business_account``.

Flow
----
    1.  Authorize (one-time) to obtain a long-lived access token.
        See: https://developers.facebook.com/docs/instagram-api/getting-started

    2.  For each Reel:
        a.  Host the MP4 temporarily at a public URL, or upload via a
            Facebook hosting endpoint.
        b.  POST ``/{ig-user-id}/media`` with ``media_type=REELS``,
            ``video_url=<public_url>`` and ``caption=...``.
        c.  Poll ``/{creation-id}?fields=status_code`` until ``FINISHED``.
        d.  POST ``/{ig-user-id}/media_publish?creation_id=<creation-id>``.

For local / dev environments the video must be hosted at a publicly
accessible URL.  This module provides a ``ReelManifest`` payload that
can be fulfilled by a separate upload / hosting step.
"""

from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings


# ---------------------------------------------------------------------------
#  Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReelPublishReceipt:
    """Record of a published Instagram Reel."""

    platform: str = "instagram"
    status: str = "published"
    media_id: str = ""
    episode_id: str = ""
    published_at: str = ""

    def as_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
#  Instagram Graph API client
# ---------------------------------------------------------------------------

API_BASE = "https://graph.facebook.com/v22.0"


class InstagramClient:
    """Minimal Instagram Graph API wrapper for Reel publishing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def _token(self) -> str:
        token = self.settings.instagram_access_token
        if not token:
            raise ValueError(
                "INSTAGRAM_ACCESS_TOKEN is not configured. "
                "Run `instagram-auth` to authorize."
            )
        return token

    @property
    def _user_id(self) -> str:
        uid = self.settings.instagram_user_id
        if not uid:
            raise ValueError(
                "INSTAGRAM_USER_ID is not configured. "
                "Run `instagram-auth` to obtain the ID."
            )
        return uid

    def create_reel_container(self, video_url: str, caption: str) -> str:
        """Create a REELS media container and return its creation ID."""
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": self._token,
        }
        result = _json_request(
            f"{API_BASE}/{self._user_id}/media",
            method="POST",
            body=urllib.parse.urlencode(params).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return str(result.get("id", ""))

    def get_container_status(self, creation_id: str) -> str:
        """Poll a media container's status code (FINISHED, IN_PROGRESS, ERROR)."""
        result = _json_request(
            f"{API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": self._token},
        )
        return str(result.get("status_code", "UNKNOWN"))

    def publish_container(self, creation_id: str) -> str:
        """Publish a finished media container and return the media ID."""
        params = {
            "creation_id": creation_id,
            "access_token": self._token,
        }
        result = _json_request(
            f"{API_BASE}/{self._user_id}/media_publish",
            method="POST",
            body=urllib.parse.urlencode(params).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return str(result.get("id", ""))

    def publish_reel(self, video_url: str, caption: str, max_poll_attempts: int = 30) -> str:
        """Create, poll, and publish a Reel. Returns the published media ID."""
        creation_id = self.create_reel_container(video_url, caption)
        if not creation_id:
            raise RuntimeError("Instagram Reel creation returned an empty ID.")

        for _ in range(max_poll_attempts):
            status = self.get_container_status(creation_id)
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError(
                    f"Instagram Reel container {creation_id} failed with status ERROR."
                )
            import time

            time.sleep(2)
        else:
            raise TimeoutError(
                f"Instagram Reel container {creation_id} did not finish "
                f"after {max_poll_attempts} polling attempts."
            )

        return self.publish_container(creation_id)


# ---------------------------------------------------------------------------
#  OAuth helpers
# ---------------------------------------------------------------------------


def instagram_authorization_url(settings: Settings) -> str:
    """Build the Instagram Graph API OAuth URL (requires a Facebook App)."""
    if not settings.instagram_client_id:
        raise ValueError("INSTAGRAM_CLIENT_ID is required for authorization.")
    redirect_uri = "http://127.0.0.1:8080/callback"
    params = {
        "client_id": settings.instagram_client_id,
        "redirect_uri": redirect_uri,
        "scope": "instagram_basic,instagram_content_publish,pages_read_engagement",
        "response_type": "code",
    }
    return (
        "https://www.facebook.com/v22.0/dialog/oauth?"
        + urllib.parse.urlencode(params)
    )


def exchange_instagram_code(settings: Settings, code: str) -> dict[str, object]:
    """Exchange an OAuth authorization code for a short-lived access token."""
    if not settings.instagram_client_secret:
        raise ValueError("INSTAGRAM_CLIENT_SECRET is required.")
    redirect_uri = "http://127.0.0.1:8080/callback"
    body = urllib.parse.urlencode(
        {
            "client_id": settings.instagram_client_id,
            "client_secret": settings.instagram_client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        }
    ).encode("utf-8")
    return _json_request(
        "https://graph.facebook.com/v22.0/oauth/access_token",
        method="POST",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def get_instagram_user_id(access_token: str, page_id: str) -> str:
    """Look up the Instagram Business Account ID for a Facebook Page."""
    result = _json_request(
        f"{API_BASE}/{page_id}",
        params={
            "fields": "instagram_business_account",
            "access_token": access_token,
        },
    )
    ig = result.get("instagram_business_account")
    if not ig:
        raise RuntimeError(
            "No Instagram Business Account linked to the Facebook Page. "
            "Ensure the Page is connected to an Instagram Business (or Creator) Account."
        )
    return str(ig["id"])


# ---------------------------------------------------------------------------
#  Authorize flow (interactive CLI)
# ---------------------------------------------------------------------------


def authorize_instagram(settings: Settings, env_path: Path) -> dict[str, str]:
    """Run the interactive OAuth flow and save credentials to .env."""
    client_id = settings.instagram_client_id
    client_secret = settings.instagram_client_secret
    if not client_id or not client_secret:
        raise ValueError(
            "INSTAGRAM_CLIENT_ID and INSTAGRAM_CLIENT_SECRET are required. "
            "Set them in .env before authorizing."
        )

    state = secrets.token_urlsafe(28)
    auth_url = instagram_authorization_url(settings)
    callback = _wait_for_oauth_callback(auth_url, state)

    if not callback.get("code"):
        raise RuntimeError("Instagram authorization did not return a code.")

    token_data = exchange_instagram_code(settings, callback["code"])
    short_token = str(token_data.get("access_token", ""))

    # Long-lived token exchange
    body = urllib.parse.urlencode(
        {
            "grant_type": "fb_exchange_token",
            "fb_exchange_token": short_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    long_token_data = _json_request(
        "https://graph.facebook.com/v22.0/oauth/access_token",
        method="POST",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access_token = str(long_token_data.get("access_token", short_token))

    # Ask user for the Facebook Page ID (we can't know it without more info)
    print(
        "\nOAuth successful! To get the Instagram Business Account ID:\n"
        "  1. Visit: https://developers.facebook.com/tools/debug/accesstoken/\n"
        "     (paste your access token)\n"
        "  2. Note the 'Scopes' include instagram_basic.\n"
        "  3. Call: "
        f"curl -X GET '{API_BASE}/me/accounts?access_token={access_token[:20]}...'\n"
        "     to find your Facebook Page ID.\n"
        "  4. Then call: "
        f"curl -X GET '{API_BASE}/{{page-id}}?fields=instagram_business_account"
        f"&access_token={access_token[:20]}...'\n"
        "     to get the Instagram Business Account ID.\n"
    )
    page_id = input("Enter your Facebook Page ID: ").strip()
    ig_user_id = get_instagram_user_id(access_token, page_id)

    _update_env(
        env_path,
        {
            "INSTAGRAM_ACCESS_TOKEN": access_token,
            "INSTAGRAM_USER_ID": ig_user_id,
        },
    )
    return {"instagram_user_id": ig_user_id}


# ---------------------------------------------------------------------------
#  Publication helpers
# ---------------------------------------------------------------------------


def instagram_publish_reel(
    video_path: Path,
    caption: str,
    video_host_url: str,
    settings: Settings,
) -> str:
    """Publish a Reel from a local MP4 hosted at a public URL.

    The video must be uploaded to a publicly accessible URL before calling
    this function.  The ``video_host_url`` is passed to the Instagram Graph
    API which fetches it server-side.

    Returns the published media ID.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Reel video not found: {video_path}")
    if not video_path.suffix.lower() == ".mp4":
        raise ValueError("Instagram Reel requires an MP4 file.")

    client = InstagramClient(settings)
    return client.publish_reel(video_host_url, caption)


def instagram_receipt_path(output_dir: Path, episode_id: str, day: str) -> Path:
    """Path to the Instagram publish receipt for an episode."""
    path = output_dir / "daily" / day / "publish"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"instagram_{episode_id}.json"


def record_instagram_publish(
    output_dir: Path,
    episode_id: str,
    day: str,
    media_id: str,
) -> dict[str, str]:
    """Record a successful Instagram publish receipt."""
    receipt = ReelPublishReceipt(
        media_id=media_id,
        episode_id=episode_id,
        published_at=datetime.now(timezone.utc).isoformat(),
    ).as_dict()
    path = instagram_receipt_path(output_dir, episode_id, day)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def assert_instagram_publish_allowed(
    output_dir: Path,
    episode_id: str,
    day: str,
    force: bool = False,
) -> None:
    """Raise if an Instagram publish receipt already exists for this episode."""
    path = instagram_receipt_path(output_dir, episode_id, day)
    if path.exists() and not force:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        raise RuntimeError(
            f"Instagram Reel already published for episode '{episode_id}' "
            f"on {day}: media_id={receipt.get('media_id', 'unknown')}. "
            "Use --force-republish to override."
        )


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------


def _json_request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, object]:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Instagram Graph API returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Instagram Graph API request failed: {exc.reason}") from exc


def _wait_for_oauth_callback(url: str, expected_state: str) -> dict[str, str]:
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if urllib.parse.urlparse(self.path).path != "/callback":
                self.send_error(404)
                return
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({key: values[0] for key, values in params.items()})
            content = (
                "<h1>Instagram connected</h1>"
                "<p>You can close this browser tab and return to the terminal.</p>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_args: Any) -> None:
            return

    print("Opening Instagram/Facebook authorization in your browser...")
    webbrowser.open(url)
    server = HTTPServer(("127.0.0.1", 8080), Handler)
    server.handle_request()
    server.server_close()
    return result


def _update_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in values:
            output.append(f"{key}={values[key]}")
            updated.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in updated:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
