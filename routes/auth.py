"""Authentication endpoints and token helpers."""
import time
import json
import hmac
import hashlib
import base64
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from database import create_user, verify_user, get_session_owner, set_user_language
from main import limiter, AUTH_SECRET, _TOKEN_TTL, SUPPORTED_LANGUAGES

router = APIRouter()


# ---------------------------------------------------------------------------
# Registration token
# ---------------------------------------------------------------------------

def _make_token(user_id: str, username: str, display_name: str) -> str:
    payload = {"uid": user_id, "un": username, "dn": display_name,
               "exp": int(time.time()) + _TOKEN_TTL}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(AUTH_SECRET, raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _verify_token(token: str) -> dict | None:
    try:
        raw, sig = token.rsplit(".", 1)
        expected = hmac.new(AUTH_SECRET, raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _require_user(request: Request) -> dict:
    """Extract + validate the auth token, return its payload, or 401. Used by
    endpoints that require login (saving is account-only)."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Login required")
    return payload


def _optional_user(request: Request) -> dict | None:
    """Like _require_user but returns None instead of raising when no valid
    token is present. Used by endpoints that allow anonymous use (chat) yet
    must trust the token over any client-sent identity when one IS present."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    return _verify_token(token) if token else None


def _assert_session_owner(user: dict, session_id: str) -> None:
    """Raise unless `user` owns `session_id`. Returns 404 (not 403) so a
    non-owner can't even confirm a session exists."""
    if get_session_owner(session_id) != user["uid"]:
        raise HTTPException(status_code=404, detail="Session not found")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(None, max_length=60)
    language: str = "en"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class LanguageRequest(BaseModel):
    language: str = Field(..., min_length=2, max_length=10)

    @field_validator("language", mode="before")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            allowed = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(f"Unsupported language '{v}'. Options: {allowed}")
        if v == "auto":
            raise ValueError("\"auto\" is a chat-time detect mode, not a storable profile language.")
        return v


@router.post("/auth/register")
@limiter.limit("10/minute")
def auth_register(request: Request, req: RegisterRequest):
    try:
        user = create_user(req.username, req.password, req.display_name, req.language)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = _make_token(user["user_id"], user["username"], user["display_name"])
    # user_id is returned so the frontend keys preferences on the ACCOUNT —
    # this is what makes personalization follow the login across devices.
    return {"authenticated": True, "token": token, "user_id": user["user_id"],
            "display_name": user["display_name"], "language": user["language"]}


@router.post("/auth/login")
@limiter.limit("20/minute")
def auth_login(request: Request, req: LoginRequest):
    user = verify_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = _make_token(user["user_id"], user["username"], user["display_name"])
    return {"authenticated": True, "token": token, "user_id": user["user_id"],
            "display_name": user["display_name"], "language": user["language"]}


@router.post("/auth/logout")
def auth_logout(request: Request):
    # Stateless tokens — nothing to invalidate server-side; the client drops it.
    return {"authenticated": False}


@router.get("/auth/me")
def auth_me(request: Request):
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # Fetch the user's stored language from the DB so the frontend can
    # enforce it on every chat request without re-logging in.
    from database import verify_user
    user = verify_user(payload["un"], None, skip_password=True)
    language = user["language"] if user else "en"
    return {"authenticated": True, "user_id": payload["uid"],
            "username": payload["un"], "display_name": payload["dn"],
            "language": language}


@router.patch("/auth/language")
def auth_language(request: Request, req: LanguageRequest):
    """Update the authenticated user's stored language preference."""
    user = _require_user(request)
    set_user_language(user["uid"], req.language)
    return {"language": req.language}
