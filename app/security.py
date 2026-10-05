import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request


class SessionSigner:
    def __init__(self, secret: str, days: int):
        self.secret = (secret or secrets.token_urlsafe(48)).encode()
        self.days = days

    def issue(self, sid: str) -> str:
        payload = json.dumps(
            {"sid": sid, "exp": int(time.time()) + self.days * 86400, "aud": "smew-chat-v2"},
            separators=(",", ":"),
        ).encode()
        body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def verify(self, token: str) -> str:
        try:
            if len(token) > 1024:
                raise ValueError()
            body, signature = token.split(".", 1)
            expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if payload["exp"] <= time.time() or payload["aud"] != "smew-chat-v2":
                raise ValueError()
            sid = payload["sid"]
            if not isinstance(sid, str) or not 20 <= len(sid) <= 64:
                raise ValueError()
            return sid
        except (ValueError, KeyError, TypeError):
            raise HTTPException(401, "Session expired. Start a new conversation.") from None

    def ip_key(self, request: Request) -> str:
        # Do not trust caller-supplied X-Forwarded-For. Uvicorn proxy parsing is disabled.
        ip = request.client.host if request.client else "unknown"
        return hmac.new(self.secret, ip.encode(), hashlib.sha256).hexdigest()[:24]


def bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 1024:
        raise HTTPException(401, "Authorization required")
    return token
