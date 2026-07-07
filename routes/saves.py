"""Saved-places endpoints (account-only)."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from database import save_place, unsave_place, get_saved_places, get_saved_slugs
from routes.auth import _require_user
from main import limiter

router = APIRouter()


class SaveRequest(BaseModel):
    slug:    str          = Field(..., min_length=1, max_length=200)
    payload: dict | None  = None


@router.post("/saves")
@limiter.limit("60/minute")
def add_save(request: Request, req: SaveRequest):
    user = _require_user(request)
    created = save_place(user["uid"], req.slug, req.payload)
    return {"saved": True, "created": created}


@router.delete("/saves/{slug}")
@limiter.limit("60/minute")
def remove_save(request: Request, slug: str):
    user = _require_user(request)
    deleted = unsave_place(user["uid"], slug)
    return {"saved": False, "deleted": deleted}


@router.get("/saves")
def list_saves(request: Request):
    """The user's saved places, full details (joined to places table)."""
    user = _require_user(request)
    places = get_saved_places(user["uid"])
    # Map to the same shape Explore/ForYou cards expect.
    out = [
        {
            "slug": p["slug"], "name": p["name"], "category": p.get("category"),
            "neighborhood": p.get("neighborhood"), "price_tier": p.get("price_tier"),
            "lat": p.get("lat"), "lng": p.get("lon"),
            "gps": ({"latitude": p.get("lat"), "longitude": p.get("lon")}
                    if p.get("lat") is not None else None),
        }
        for p in places
    ]
    return {"count": len(out), "places": out}


@router.get("/saves/slugs")
def list_save_slugs(request: Request):
    """Just the slugs the user has saved — lets the frontend mark saved cards
    without fetching full details."""
    user = _require_user(request)
    return {"slugs": get_saved_slugs(user["uid"])}
