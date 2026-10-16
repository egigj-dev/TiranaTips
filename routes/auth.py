"""Authentication endpoints and token helpers."""
import time
import json
import hmac
import hashlib
import base64
import database
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from database import create_user, verify_user, get_session_owner, set_user_language
from main import limiter, AUTH_SECRET, _TOKEN_TTL, SUPPORTED_LANGUAGES

router = APIRouter()


# ---------------------------------------------------------------------------
# Registration token
# ---------------------------------------------------------------------------

# Uses the account version so password changes revoke earlier signed tokens.
def _make_token(user_id: str, username: str, display_name: str, token_version: int) -> str:
    payload = {"uid": user_id, "un": username, "dn": display_name,
               "exp": int(time.time()) + _TOKEN_TTL, "tv": token_version}
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
    if not _auth_state_matches(payload):
        raise HTTPException(status_code=401, detail="Login required")
    return payload


def _optional_user(request: Request) -> dict | None:
    """Like _require_user but returns None instead of raising when no valid
    token is present. Used by endpoints that allow anonymous use (chat) yet
    must trust the token over any client-sent identity when one IS present."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    payload = _verify_token(token) if token else None
    return payload if _auth_state_matches(payload) else None


def _assert_session_owner(user: dict, session_id: str) -> None:
    """Raise unless `user` owns `session_id`. Returns 404 (not 403) so a
    non-owner can't even confirm a session exists."""
    if get_session_owner(session_id) != user["uid"]:
        raise HTTPException(status_code=404, detail="Session not found")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r'^[A-Za-z0-9_.-]+$')
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
    token = _make_token(user["user_id"], user["username"], user["display_name"], user["token_version"])
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
    token = _make_token(user["user_id"], user["username"], user["display_name"], user["token_version"])
    return {"authenticated": True, "token": token, "user_id": user["user_id"],
            "display_name": user["display_name"], "language": user["language"]}


@router.post("/auth/logout")
def auth_logout(request: Request):
    # Stateless tokens — nothing to invalidate server-side; the client drops it.
    return {"authenticated": False}


@router.get("/auth/me")
def auth_me(request: Request):
    payload = _require_user(request)
    # Read language by uid so preserved case-duplicate accounts cannot cross rows.
    user = database.get_user_credentials(payload["uid"])
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    language = user["language"] or "en"
    return {"authenticated": True, "user_id": payload["uid"],
            "username": payload["un"], "display_name": payload["dn"],
            "language": language}


@router.patch("/auth/language")
def auth_language(request: Request, req: LanguageRequest):
    """Update the authenticated user's stored language preference."""
    user = _require_user(request)
    set_user_language(user["uid"], req.language)
    return {"language": req.language}


# Uses a verified payload's uid and tv, including legacy tokens with version zero.
def _auth_state_matches(payload: dict | None) -> bool:
    if not payload:
        return False
    state = database.get_user_auth_state(payload.get("uid"))
    return state is not None and payload.get("tv", 0) == state["token_version"]


# Uses the authenticated uid and current password to bind mutations to one row.
def _current_credentials(user: dict, password: str) -> dict:
    row = database.get_user_credentials(user["uid"])
    if (not row or row["token_version"] != user.get("tv", 0)
            or not hmac.compare_digest(database._hash_password(password, row["salt"]), row["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid current password")
    return row


# Password fields use the same bounds as registration and login.
class PasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


# The password confirms account deletion without trusting client-supplied identities.
class DeleteAccountRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


# Uses request identity and verified credentials to replace the password and token.
@router.patch("/auth/password")
@limiter.limit("5/minute")
def auth_password(request: Request, req: PasswordRequest):
    user = _require_user(request)
    row = _current_credentials(user, req.current_password)
    version = database.change_user_password(user["uid"], req.new_password,
                                           row["password_hash"], row["token_version"])
    if version is None:
        raise HTTPException(status_code=409, detail="Account changed; please sign in again")
    token = _make_token(user["uid"], row["username"], row["display_name"], version)
    return {"token": token}


# Uses request identity and verified credentials for a conditional account deletion.
@router.delete("/auth/account")
@limiter.limit("5/minute")
def auth_delete_account(request: Request, req: DeleteAccountRequest):
    user = _require_user(request)
    row = _current_credentials(user, req.password)
    if not database.delete_user_account(user["uid"], row["password_hash"], row["token_version"]):
        raise HTTPException(status_code=409, detail="Account changed; please sign in again")
    return {"deleted": True}
