"""Events endpoint for the Explore page."""
from datetime import date, timedelta
from fastapi import APIRouter, Request

from database import query_events
from main import limiter

router = APIRouter()


@router.get("/events")
@limiter.limit("60/minute")
def list_events(request: Request, days: int = 30, category: str | None = None,
                municipality: str | None = None, limit: int = 50):
    """Upcoming events for the Explore page — canonical (deduped) events from
    today through `days` ahead, soonest first. Reads the same table the chat's
    event answers use, so the two never disagree."""
    today = date.today().isoformat()
    until = (date.today() + timedelta(days=days)).isoformat()
    events = query_events(
        date_from=today, date_to=until, category=category,
        municipality=municipality, canonical_only=True, limit=limit,
    )
    out = [
        {
            "title":       e["title"],
            "description": e["description"],
            "category":    e["category"],
            "start_date":  e["start_date"],
            "end_date":    e["end_date"],
            "venue":       e.get("municipality"),
            "image_url":   e["image_url"],
            "ticket_url":  e["ticket_url"],
            "source_url":  e["source_url"],
        }
        for e in events
    ]
    return {"count": len(out), "events": out}
