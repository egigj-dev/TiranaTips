import { useState, useRef } from "react";
import "./explore.css";
import {
  Search,
  Star,
  MapPin,
  ExternalLink,
  UtensilsCrossed,
  Wine,
  Landmark,
  Coffee,
  Moon,
  Trees,
  CalendarDays,
  Ticket,
} from "lucide-react";

import { explorePlaces, browsePlaces, getEvents } from "../../lib/api";

// Categories are preset queries sent to the same /places/explore endpoint.
// label = chip text; browseCat = our stored `category` value (matches the OSM
// ingestion buckets); query = semantic hint sent to browse's vector side.
const CATEGORIES = [
  { key: "eat", label: "Eat", icon: UtensilsCrossed, browseCat: "eat", query: "restaurant" },
  { key: "drink", label: "Drink", icon: Wine, browseCat: "drink", query: "bar" },
  { key: "cafe", label: "Cafés", icon: Coffee, browseCat: "cafe", query: "coffee" },
  { key: "see", label: "See", icon: Landmark, browseCat: "see", query: "attraction museum" },
  { key: "nightlife", label: "Nightlife", icon: Moon, browseCat: "nightlife", query: "nightclub" },
  { key: "outdoors", label: "Outdoors", icon: Trees, browseCat: "outdoors", query: "park" },
];

// Neighborhoods with real coverage (from the enrichment pass). Kept in sync
// with places_enrich.py's boxes.
const NEIGHBORHOODS = [
  "Blloku", "Tirana e Re", "21 Dhjetori", "Qendra",
  "Myslym Shyri", "Pazari i Ri", "Komuna e Parisit", "Liqeni / Grand Park",
];

function Explore() {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeCat, setActiveCat] = useState(null);
  const [activeHood, setActiveHood] = useState("");
  const [searchText, setSearchText] = useState("");
  const [openOnly, setOpenOnly] = useState(false);
  const [minRating, setMinRating] = useState(0);
  const [hasSearched, setHasSearched] = useState(false);
  // Monotonic request id. Every fetch captures the current value; when it
  // resolves, it only commits results if it's STILL the latest request.
  // Without this, clicking chips fast lets a slow response (e.g. cafes, with
  // 12 enrichment calls) land after a newer one and overwrite it — you'd see
  // parks under the Cafés chip. This is the "stays same / wrong category" bug.
  const reqId = useRef(0);
  // Events mode: when on, the page shows upcoming events instead of places.
  const [mode, setMode] = useState("places"); // "places" | "events"
  const [events, setEvents] = useState([]);

  const showEvents = async () => {
    const myReq = ++reqId.current;
    setMode("events");
    setLoading(true);
    setError("");
    setActiveCat(null);
    try {
      const { events: list } = await getEvents(30);
      if (myReq !== reqId.current) return; // a newer request superseded this
      setEvents(list || []);
    } catch {
      if (myReq !== reqId.current) return;
      setError("Couldn’t load events right now. Please try again.");
      setEvents([]);
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  };

  // Free-text search → Google (broad coverage, anything goes).
  const runTextSearch = async (query) => {
    if (!query.trim()) return;
    const myReq = ++reqId.current;
    setMode("places");
    setLoading(true);
    setError("");
    setActiveCat(null);
    setActiveHood("");
    setHasSearched(true);
    try {
      const { places } = await explorePlaces(query.trim());
      if (myReq !== reqId.current) return;
      setResults(places || []);
    } catch {
      if (myReq !== reqId.current) return;
      setError("Couldn’t load places right now. Please try again.");
      setResults([]);
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  };

  // Category (+ optional neighborhood) → browse our owned, filterable index,
  // enriched with live Google fields so cards stay rich.
  const runCategory = async (cat, hood) => {
    const myReq = ++reqId.current;
    setMode("places");
    setLoading(true);
    setError("");
    setActiveCat(cat.key);
    setSearchText("");
    setHasSearched(true);
    try {
      const { places } = await browsePlaces({
        query: cat.query,
        category: cat.browseCat,
        neighborhood: hood || null,
        limit: 12,
      });
      if (myReq !== reqId.current) return;
      setResults(places || []);
    } catch {
      if (myReq !== reqId.current) return;
      setError("Couldn’t load places right now. Please try again.");
      setResults([]);
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  };

  // Changing the neighborhood dropdown re-runs the active category.
  const onHoodChange = (hood) => {
    setActiveHood(hood);
    const cat = CATEGORIES.find((c) => c.key === activeCat);
    if (cat) runCategory(cat, hood);
  };

  // Filters are client-side over the fetched result set — no extra API calls.
  const filtered = results.filter((p) => {
    if (openOnly && p.open_now !== "Open") return false;
    if (minRating && (p.rating ?? 0) < minRating) return false;
    return true;
  });

  return (
    <main className="explore-page">
      <header className="explore-header">
        <h1>Explore Tirana</h1>
        <p>Search any place, or browse by category and area.</p>

        <div className="explore-search">
          <Search size={18} />
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runTextSearch(searchText)}
            placeholder="Try “rooftop bar”, “Italian restaurant”, “museum”…"
            maxLength={200}
          />
          <button type="button" onClick={() => runTextSearch(searchText)}>
            Search
          </button>
        </div>

        <div className="explore-categories">
          {CATEGORIES.map((c) => {
            const Icon = c.icon;
            return (
              <button
                key={c.key}
                type="button"
                className={
                  "category-chip" + (activeCat === c.key ? " category-active" : "")
                }
                onClick={() => runCategory(c, activeHood)}
              >
                <Icon size={16} />
                {c.label}
              </button>
            );
          })}

          {/* Neighborhood filter only applies to category browsing (our owned
              index has neighborhoods; free-text Google results don't). */}
          {activeCat && (
            <select
              className="hood-select"
              value={activeHood}
              onChange={(e) => onHoodChange(e.target.value)}
            >
              <option value="">All areas</option>
              {NEIGHBORHOODS.map((h) => (
                <option key={h} value={h}>{h}</option>
              ))}
            </select>
          )}

          {/* Events chip — switches the page to upcoming events. */}
          <button
            type="button"
            className={
              "category-chip events-chip" + (mode === "events" ? " category-active" : "")
            }
            onClick={showEvents}
          >
            <CalendarDays size={16} />
            Events
          </button>
        </div>

        {mode === "places" && hasSearched && !loading && results.length > 0 && (
          <div className="explore-filters">
            <label className="filter-toggle">
              <input
                type="checkbox"
                checked={openOnly}
                onChange={(e) => setOpenOnly(e.target.checked)}
              />
              Open now
            </label>
            <label className="filter-rating">
              Min rating
              <select
                value={minRating}
                onChange={(e) => setMinRating(Number(e.target.value))}
              >
                <option value={0}>Any</option>
                <option value={3}>3.0+</option>
                <option value={4}>4.0+</option>
                <option value={4.5}>4.5+</option>
              </select>
            </label>
            <span className="filter-count">
              {filtered.length} of {results.length}
            </span>
          </div>
        )}
      </header>

      <section className="explore-results">
        {loading && <p className="explore-status">Loading…</p>}
        {error && <p className="explore-status explore-error">{error}</p>}

        {mode === "events" ? (
          <>
            {!loading && !error && events.length === 0 && (
              <p className="explore-status">No upcoming events in the next 30 days.</p>
            )}
            <div className="explore-grid">
              {events.map((ev, i) => {
                const when = new Date(ev.start_date).toLocaleDateString("en-US", {
                  weekday: "short", month: "short", day: "numeric",
                });
                const link = ev.ticket_url || ev.source_url;
                const Card = link ? "a" : "div";
                const linkProps = link
                  ? { href: link, target: "_blank", rel: "noreferrer" }
                  : {};
                return (
                  <Card
                    key={ev.title + i}
                    className="place-card event-card"
                    {...linkProps}
                  >
                    <div className="place-card-head">
                      <h3>{ev.title}</h3>
                      {link && <ExternalLink size={15} className="place-card-ext" />}
                    </div>
                    <div className="place-meta">
                      <span className="event-date">
                        <CalendarDays size={13} /> {when}
                      </span>
                      {ev.category && <span className="place-type">{ev.category}</span>}
                    </div>
                    {ev.venue && (
                      <p className="place-address">
                        <MapPin size={13} /> {ev.venue}
                      </p>
                    )}
                    {ev.ticket_url && (
                      <span className="event-ticket">
                        <Ticket size={13} /> Tickets
                      </span>
                    )}
                  </Card>
                );
              })}
            </div>
          </>
        ) : (
          <>
            {!loading && !error && hasSearched && filtered.length === 0 && (
              <p className="explore-status">No places match those filters.</p>
            )}
            {!loading && !hasSearched && (
              <p className="explore-status">
                Pick a category or search to see places.
              </p>
            )}

            <div className="explore-grid">
              {filtered.map((p, i) => (
                <a
                  key={p.slug || p.place_id || `${p.name}-${i}`}
                  className="place-card"
                  href={p.maps_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <div className="place-card-head">
                    <h3>{p.name}</h3>
                    <ExternalLink size={15} className="place-card-ext" />
                  </div>

                  {p.type && <span className="place-type">{p.type}</span>}

                  <div className="place-meta">
                    {p.rating != null && (
                      <span className="place-rating">
                        <Star size={13} fill="currentColor" /> {p.rating}
                        {p.reviews != null && (
                          <em>({p.reviews.toLocaleString()})</em>
                        )}
                      </span>
                    )}
                    {p.price && <span className="place-price">{p.price}</span>}
                    {p.open_now && (
                      <span
                        className={
                          "place-open " +
                          (p.open_now === "Open" ? "is-open" : "is-closed")
                        }
                      >
                        {p.open_now}
                      </span>
                    )}
                  </div>

                  {p.address && (
                    <p className="place-address">
                      <MapPin size={13} /> {p.address}
                    </p>
                  )}
                </a>
              ))}
            </div>
          </>
        )}
      </section>
    </main>
  );
}

export default Explore;