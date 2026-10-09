import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time

from fastapi import HTTPException, Request


def client_ip(request: Request, header: str = "", trust_forwarded_for: bool = False) -> str:
    """Visitor IP for rate limits.

    Uvicorn proxy parsing is disabled, so the socket peer is Railway's edge proxy. The edge overwrites
    X-Real-IP on every public request; X-Forwarded-For is used only when explicitly trusted.
    """
    candidates = [request.headers.get(header, "")] if header else []
    if trust_forwarded_for:
        candidates.append(request.headers.get("x-forwarded-for", "").split(",")[0])
    for value in candidates:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            continue
    return request.client.host if request.client else "unknown"


class SessionSigner:
    def __init__(self, secret: str, days: int, ip_header: str = "", trust_forwarded_for: bool = False):
        self.secret = (secret or secrets.token_urlsafe(48)).encode()
        self.days = days
        self.ip_header, self.trust_forwarded_for = ip_header, trust_forwarded_for

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
        ip = client_ip(request, self.ip_header, self.trust_forwarded_for)
        return hmac.new(self.secret, ip.encode(), hashlib.sha256).hexdigest()[:24]


def bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 1024:
        raise HTTPException(401, "Authorization required")
    return token


# Indian mobile numbers, optionally with +91/0 and spaces or dashes between digits.
PHONE_RE = re.compile(r"(?<![\w+])(?:\+?91[\s-]?|0)?[6-9](?:[\s-]?\d){9}(?!\d)")


def redact_phones(message: str, keep: tuple[str, ...] = ()) -> tuple[str, bool]:
    """Mask phone numbers typed into chat (all but the last two digits) before storage or the LLM.

    Numbers in `keep` (the workshop's own) stay readable. Returns the text and whether a number was found.
    """
    found = False

    def mask(match: re.Match) -> str:
        nonlocal found
        digits = re.sub(r"\D", "", match.group(0))
        if digits[-10:] in keep:
            return match.group(0)
        found = True
        hidden = len(digits) - 2
        out = []
        for char in match.group(0):
            if char.isdigit() and hidden > 0:
                out.append("X")
                hidden -= 1
            else:
                out.append(char)
        return "".join(out)

    return PHONE_RE.sub(mask, message), found
