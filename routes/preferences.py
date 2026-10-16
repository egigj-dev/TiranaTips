# @router.get("/preferences/{user_id}")
# def read_preferences(user_id: str = Path(..., pattern=USER_ID_PATTERN)):
#     """
#     Return preferences for a user, or an "empty" object if the user has
#     never set any. Always returns 200 — a brand-new user is a normal case,
#     not an error, and the frontend uses the all-null response to decide
#     whether to show onboarding.
#     """
#     prefs = get_user_preferences(user_id)
#     if prefs is None:
#         return {
#             "user_id": user_id,
#             "mode": None, "currency": None, "price_tier": None,
#             "interests": [], "location_ok": None,
#             "created_at": None, "updated_at": None,
#             "onboarded": False,
#         }
#     return {**prefs, "onboarded": _is_onboarded(prefs)}

# @router.put("/preferences/{user_id}")
# @limiter.limit("30/minute")
# def write_preferences(
#     request: Request,
#     req: PreferencesRequest,
#     user_id: str = Path(..., pattern=USER_ID_PATTERN),
# ):
#     """
#     Upsert preferences. Partial updates supported: any field left out is
#     preserved. This means the onboarding flow can call PUT once per screen
#     instead of buffering everything and submitting at the end — which is
#     what we want, because users routinely abandon partway through.
#     """
#     prefs = save_user_preferences(
#         user_id,
#         mode=req.mode,
#         currency=req.currency,
#         price_tier=req.price_tier,
#         interests=req.interests,
#         neighborhoods=req.neighborhoods,
#         location_ok=req.location_ok,
#     )
#     return {**prefs, "onboarded": _is_onboarded(prefs)}

# @router.delete("/preferences/{user_id}")
# def reset_preferences(user_id: str = Path(..., pattern=USER_ID_PATTERN)):
#     """
#     Wipe preferences for a user. Useful for a "redo onboarding" flow or
#     GDPR-style data deletion. Chat history is intentionally NOT touched
#     — that's a separate concern, deleted via the existing session endpoints.
#     """
#     deleted = delete_user_preferences(user_id)
#     return {"deleted": deleted}

"""Onboarding preferences endpoints. Anonymous users only — user_id is
whatever UUID the client generated and kept in localStorage. There's no auth
check here; with no accounts there is no concept of "spoofing" another user.
When we add real auth later, add a dependency that asserts the request's
authenticated user matches the path parameter."""
from fastapi import APIRouter, Path, Request, HTTPException
from pydantic import BaseModel, Field, field_validator

from database import get_user_preferences, save_user_preferences, delete_user_preferences
from main import (
    limiter, PREFERENCE_MODES, PREFERENCE_PRICE_TIERS, PREFERENCE_CURRENCIES,
    PREFERENCE_INTERESTS, PREFERENCE_NEIGHBORHOODS, USER_ID_PATTERN,
)
from routes.auth import _require_user

router = APIRouter()


def _authorize_prefs(request: Request, user_id: str) -> None:
    """Preferences are keyed either on an anonymous client id or on an account
    id. Account ids are minted as 'u_' + hex (see create_user), so they must be
    protected: require a valid token whose uid matches. Anonymous ids stay open
    — they're unguessable localStorage secrets under the original design, with
    no account to spoof."""
    if user_id.startswith("u_"):
        user = _require_user(request)
        if user["uid"] != user_id:
            raise HTTPException(status_code=404, detail="Not found")


class PreferencesRequest(BaseModel):
    """
    Onboarding preferences. All fields optional so the client can save a
    single screen at a time (mode now, currency on the next screen, etc.)
    without overwriting prior choices. The database helper merges the
    payload into the existing row.

    Empty string / empty list explicitly CLEAR a field — useful for a
    "reset this preference" flow. Use None (omit the key) to leave a
    field unchanged.
    """
    mode:        str       | None = None
    currency:    str       | None = None
    price_tier:  str       | None = None
    interests:   list[str] | None = None
    neighborhoods: list[str] | None = None
    location_ok: bool      | None = None

    @field_validator("mode")
    @classmethod
    def _mode_in_set(cls, v):
        if v in (None, ""): return v
        if v not in PREFERENCE_MODES:
            raise ValueError(f"mode must be one of {PREFERENCE_MODES}")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_in_set(cls, v):
        if v in (None, ""): return v
        if v not in PREFERENCE_CURRENCIES:
            raise ValueError(f"currency must be one of {PREFERENCE_CURRENCIES}")
        return v

    @field_validator("price_tier")
    @classmethod
    def _price_in_set(cls, v):
        if v in (None, ""): return v
        if v not in PREFERENCE_PRICE_TIERS:
            raise ValueError(f"price_tier must be one of {PREFERENCE_PRICE_TIERS}")
        return v

    @field_validator("interests")
    @classmethod
    def _interests_in_set(cls, v):
        if v is None: return v
        # Allow empty list (clears the field) but reject unknown values.
        bad = [x for x in v if x not in PREFERENCE_INTERESTS]
        if bad:
            raise ValueError(f"unknown interests: {bad}. Allowed: {PREFERENCE_INTERESTS}")
        return list(dict.fromkeys(v))  # de-dupe while preserving order

    @field_validator("neighborhoods")
    @classmethod
    def _neighborhoods_in_set(cls, v):
        if v is None: return v
        bad = [x for x in v if x not in PREFERENCE_NEIGHBORHOODS]
        if bad:
            raise ValueError(f"unknown neighborhoods: {bad}. Allowed: {PREFERENCE_NEIGHBORHOODS}")
        return list(dict.fromkeys(v))


def _is_onboarded(prefs: dict) -> bool:
    """
    A user counts as "onboarded" once they've made at least one meaningful
    choice. The frontend uses this to decide whether to redirect to /onboard
    on first chat. We deliberately don't require ALL fields — many users
    will skip currency or interests and that's fine; the experience just
    falls back to defaults for the un-set ones.
    """
    return any([
        prefs.get("mode"),
        prefs.get("currency"),
        prefs.get("price_tier"),
        prefs.get("interests"),
        prefs.get("neighborhoods"),
    ])


@router.get("/preferences/options")
def preferences_options():
    """
    Canonical option lists for the onboarding UI. Frontend fetches this
    on app load and renders the choice screens from the response, so
    adding a new interest or mode never requires a frontend deploy.
    """
    return {
        "modes":       PREFERENCE_MODES,
        "price_tiers": PREFERENCE_PRICE_TIERS,
        "currencies":  PREFERENCE_CURRENCIES,
        "interests":   PREFERENCE_INTERESTS,
        "neighborhoods": PREFERENCE_NEIGHBORHOODS,
    }


@router.get("/preferences/{user_id}")
def read_preferences(request: Request, user_id: str = Path(..., pattern=USER_ID_PATTERN)):
    """
    Return preferences for a user, or an "empty" object if the user has
    never set any. Always returns 200 — a brand-new user is a normal case,
    not an error, and the frontend uses the all-null response to decide
    whether to show onboarding.
    """
    _authorize_prefs(request, user_id)
    prefs = get_user_preferences(user_id)
    if prefs is None:
        return {
            "user_id": user_id,
            "mode": None, "currency": None, "price_tier": None,
            "interests": [], "location_ok": None,
            "created_at": None, "updated_at": None,
            "onboarded": False,
        }
    return {**prefs, "onboarded": _is_onboarded(prefs)}


@router.put("/preferences/{user_id}")
@limiter.limit("30/minute")
def write_preferences(
    request: Request,
    req: PreferencesRequest,
    user_id: str = Path(..., pattern=USER_ID_PATTERN),
):
    """
    Upsert preferences. Partial updates supported: any field left out is
    preserved. This means the onboarding flow can call PUT once per screen
    instead of buffering everything and submitting at the end — which is
    what we want, because users routinely abandon partway through.
    """
    _authorize_prefs(request, user_id)
    prefs = save_user_preferences(
        user_id,
        mode=req.mode,
        currency=req.currency,
        price_tier=req.price_tier,
        interests=req.interests,
        neighborhoods=req.neighborhoods,
        location_ok=req.location_ok,
    )
    return {**prefs, "onboarded": _is_onboarded(prefs)}


@router.delete("/preferences/{user_id}")
def reset_preferences(request: Request, user_id: str = Path(..., pattern=USER_ID_PATTERN)):
    """
    Wipe preferences for a user. Useful for a "redo onboarding" flow or
    GDPR-style data deletion. Chat history is intentionally NOT touched
    — that's a separate concern, deleted via the existing session endpoints.
    """
    _authorize_prefs(request, user_id)
    deleted = delete_user_preferences(user_id)
    return {"deleted": deleted}