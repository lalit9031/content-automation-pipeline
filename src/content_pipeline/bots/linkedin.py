from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage
from content_pipeline.storage import LocalDailyStorage


@dataclass(frozen=True)
class PublishReceipt:
    platform: str
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "status": self.status,
            "message": self.message,
        }


class LinkedInClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authorization_url(self, state: str) -> str:
        if not self.settings.linkedin_client_id:
            raise ValueError("LINKEDIN_CLIENT_ID is required")
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.linkedin_client_id,
                "redirect_uri": self.settings.linkedin_redirect_uri,
                "state": state,
                "scope": "openid profile email w_member_social",
            }
        )
        return f"https://www.linkedin.com/oauth/v2/authorization?{query}"

    def exchange_code(self, code: str) -> dict[str, object]:
        if not self.settings.linkedin_client_secret:
            raise ValueError("LINKEDIN_CLIENT_SECRET is required")
        body = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.settings.linkedin_client_id,
                "client_secret": self.settings.linkedin_client_secret,
                "redirect_uri": self.settings.linkedin_redirect_uri,
            }
        ).encode("utf-8")
        return _json_request(
            "https://www.linkedin.com/oauth/v2/accessToken",
            method="POST",
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def userinfo(self, token: str) -> dict[str, object]:
        return _json_request(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )

    def register_image(self, token: str, member_urn: str) -> tuple[str, str]:
        payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": member_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }
        result = _json_request(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            method="POST",
            body=json.dumps(payload).encode("utf-8"),
            headers=_linkedin_headers(token),
        )
        value = result["value"]
        mechanism = value["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]
        return str(mechanism["uploadUrl"]), str(value["asset"])

    def upload_image(self, token: str, upload_url: str, image_path: Path) -> None:
        _request(
            upload_url,
            method="PUT",
            body=image_path.read_bytes(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
            },
        )

    def create_image_post(
        self,
        token: str,
        member_urn: str,
        package: ContentPackage,
        asset_urn: str,
    ) -> str:
        payload = linkedin_share_payload(member_urn, package, asset_urn)
        response = _request(
            "https://api.linkedin.com/v2/ugcPosts",
            method="POST",
            body=json.dumps(payload).encode("utf-8"),
            headers=_linkedin_headers(token),
        )
        return response.headers.get("X-RestLi-Id", "published")


def linkedin_share_payload(
    member_urn: str,
    package: ContentPackage,
    asset_urn: str,
) -> dict[str, object]:
    caption = " ".join([package.linkedin_caption, *package.hashtags])
    return {
        "author": member_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": caption},
                "shareMediaCategory": "IMAGE",
                "media": [
                    {
                        "status": "READY",
                        "media": asset_urn,
                        "title": {"text": package.seo_title},
                    }
                ],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }


def authorize_linkedin(settings: Settings, env_path: Path) -> str:
    client = LinkedInClient(settings)
    state = secrets.token_urlsafe(28)
    callback = _wait_for_oauth_callback(client.authorization_url(state))
    if callback.get("state") != state:
        raise RuntimeError("LinkedIn authorization state mismatch")
    if "error" in callback:
        raise RuntimeError(f"LinkedIn authorization failed: {callback['error']}")
    token_data = client.exchange_code(callback["code"])
    access_token = str(token_data["access_token"])
    userinfo = client.userinfo(access_token)
    member_urn = f"urn:li:person:{userinfo['sub']}"
    _update_env(
        env_path,
        {
            "LINKEDIN_ACCESS_TOKEN": access_token,
            "LINKEDIN_MEMBER_URN": member_urn,
        },
    )
    return member_urn


def publish_linkedin_image(
    package: ContentPackage,
    image_path: Path,
    settings: Settings,
) -> str:
    if not settings.linkedin_access_token or not settings.linkedin_member_urn:
        raise ValueError("Run linkedin-auth before publishing")
    if image_path.suffix.lower() != ".png":
        raise ValueError("LinkedIn live publishing requires a generated PNG image")
    client = LinkedInClient(settings)
    upload_url, asset_urn = client.register_image(
        settings.linkedin_access_token, settings.linkedin_member_urn
    )
    client.upload_image(settings.linkedin_access_token, upload_url, image_path)
    return client.create_image_post(
        settings.linkedin_access_token,
        settings.linkedin_member_urn,
        package,
        asset_urn,
    )


def prepare_linkedin_post(
    package: ContentPackage,
    image_file: str,
    settings: Settings,
    storage: LocalDailyStorage,
) -> PublishReceipt:
    if settings.publish_linkedin:
        raise NotImplementedError(
            "Live LinkedIn publishing is intentionally gated until member OAuth "
            "with w_member_social and the image upload/post flow are configured."
        )
    post = {
        "posting_target": "personal_profile",
        "author": settings.linkedin_member_urn or "authenticated_member",
        "required_scope": "w_member_social",
        "caption": package.linkedin_caption,
        "hashtags": package.hashtags,
        "image_file": image_file,
    }
    storage.write_json(package.date, "publish/linkedin_payload.json", post)
    receipt = PublishReceipt(
        platform="linkedin",
        status="prepared",
        message="Personal profile payload prepared locally; public posting is disabled.",
    )
    storage.write_json(package.date, "publish/linkedin_receipt.json", receipt.as_dict())
    return receipt


def _linkedin_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        return urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LinkedIn API returned {exc.code}: {detail}") from exc


def _json_request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    response = _request(url, method=method, body=body, headers=headers)
    return json.loads(response.read().decode("utf-8"))


def _wait_for_oauth_callback(authorization_url: str) -> dict[str, str]:
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if urllib.parse.urlparse(self.path).path != "/callback":
                self.send_error(404)
                return
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({key: values[0] for key, values in params.items()})
            content = (
                "<h1>LinkedIn connected</h1>"
                "<p>You can close this browser tab and return to the terminal.</p>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_args) -> None:
            return

    print("Opening LinkedIn authorization in your browser...")
    webbrowser.open(authorization_url)
    server = HTTPServer(("localhost", 8080), Handler)
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
