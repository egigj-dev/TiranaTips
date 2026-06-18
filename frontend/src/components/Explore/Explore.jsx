import { useState, useRef, useEffect } from "react";
import "./explore.css";
import {
  Search,
  Star,
  MapPin,
  ExternalLink,
  Bookmark,
  UtensilsCrossed,
  Wine,
  Landmark,
  Coffee,
  Moon,
  Trees,
  CalendarDays,
  Ticket,
} from "lucide-react";

import {
  explorePlaces,
  browsePlaces,
  getEvents,
  savePlace,
  unsavePlace,
  getSavedSlugs,
  getSessionToken,
  getPreferences,
  getUserId,
  getAlsoSaved,
} from "../../lib/api";

const CATEGORIES = [
  { key: "eat", label: "Eat", icon: UtensilsCrossed, browseCat: "eat", query: "restaurant" },
  { key: "drink", label: "Drink", icon: Wine, browseCat: "drink", query: "bar" },
  { key: "cafe", label: "Cafés", icon: Coffee, browseCat: "cafe", query: "coffee" },
  { key: "see", label: "See", icon: Landmark, browseCat: "see", query: "attraction museum" },
  { key: "nightlife", label: "Nightlife", icon: Moon, browseCat: "nightlife", query: "nightclub" },
  { key: "outdoors", label: "Outdoors", icon: Trees, browseCat: "outdoors", query: "park" },
];

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
  const reqId = useRef(0);
  const [mode, setMode] = useState("places"); // "places" | "events"
  const [events, setEvents] = useState([]);

  // Saved places (by slug). Login-required: loaded only when a token exists.
  const [savedSlugs, setSavedSlugs] = useState([]);
  const [toast, setToast] = useState("");

  // User preferences for auto-filtering Browse results.
  const [userPrefs, setUserPrefs] = useState(null);

  // Collaborative 'people also saved' recommendations
  const [alsoSaved, setAlsoSaved] = useState([]);
  const [alsoSavedSlug, setAlsoSavedSlug] = useState(null);
  const [alsoSavedLoading, setAlsoSavedLoading] = useState(false);

  useEffect(() => {
    if (getSessionToken()) {
      getSavedSlugs()
        .then((r) => setSavedSlugs(r.slugs || []))
        .catch(() => {});
      getPreferences()
        .then((p) => setUserPrefs(p))
        .catch(() => {});
    }
  }, []);

  // When results change, load collaborative 'people also saved' for the first
  // owned place (has a slug) — seeded by .slug, not Google's g:<place_id>.
  useEffect(() => {
    const owned = results.find((p) => p.slug);
    const targetSlug = owned?.slug;
    if (!targetSlug || targetSlug === alsoSavedSlug) return;
    setAlsoSavedSlug(targetSlug);
    setAlsoSavedLoading(true);
    getAlsoSaved(targetSlug, 4)
      .then((r) => setAlsoSaved(r.places || []))
      .catch(() => setAlsoSaved([]))
      .finally(() => setAlsoSavedLoading(false));
  }, [results]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  };

  // A saved place is referenced by its owned slug, or — for Google text-search
  // results, which aren't in our places table — a namespaced 'g:<place_id>'.
  // The namespace can't collide with an OSM slug and tells the backend to
  // store the card's payload instead of relying on a join.
  const placeRef = (p) => p.slug || (p.place_id ? `g:${p.place_id}` : null);

  // Self-describing card data sent only for external (Google) saves.
  const externalPayload = (p) => ({
    name: p.name,
    type: p.type,
    address: p.address,
    maps_url: p.maps_url,
    rating: p.rating,
    reviews: p.reviews,
    price: p.price,
    gps: p.gps,
  });

  const toggleSave = async (e, p) => {
    // Cards are <a> tags — stop the click from navigating away.
    e.preventDefault();
    e.stopPropagation();
    if (!getSessionToken()) {
      showToast("Log in to save places");
      return;
    }
    const ref = placeRef(p);
    if (!ref) return;
    const isSaved = savedSlugs.includes(ref);
    setSavedSlugs((prev) =>
      isSaved ? prev.filter((s) => s !== ref) : [...prev, ref]
    );
    try {
      if (isSaved) await unsavePlace(ref);
      // Owned places live in our table (no payload needed); Google results
      // carry their card data so saved places can render without a join.
      else await savePlace(ref, p.slug ? null : externalPayload(p));
    } catch {
      // Revert on failure.
      setSavedSlugs((prev) =>
        isSaved ? [...prev, ref] : prev.filter((s) => s !== ref)
      );
      showToast("Couldn't update saved places");
    }
  };

  const showEvents = async () => {
    const myReq = ++reqId.current;
    setMode("events");
    setLoading(true);
    setError("");
    setActiveCat(null);
    try {
      const { events: list } = await getEvents(30, null, "Tiranë");
      if (myReq !== reqId.current) return;
      setEvents(list || []);
    } catch {
      if (myReq !== reqId.current) return;
      setError("Couldn’t load events right now. Please try again.");
      setEvents([]);
    } finally {
      if (myReq === reqId.current) setLoading(false);
    }
  };

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

  const runCategory = async (cat, hood) => {
    const myReq = ++reqId.current;
    setMode("places");
    setLoading(true);
    setError("");
    setActiveCat(cat.key);
    setSearchText("");
    setHasSearched(true);
    // Auto-filter by the user's price_tier + interests if logged in
    const isLoggedIn = getSessionToken();
    const maxPrice = isLoggedIn && userPrefs?.price_tier
      ? userPrefs.price_tier : undefined;
    try {
      const { places } = await browsePlaces({
        query: cat.query,
        category: cat.browseCat,
        neighborhood: hood || null,
        max_price: maxPrice,
        user_id: isLoggedIn ? getUserId() : undefined,
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

  const onHoodChange = (hood) => {
    setActiveHood(hood);
    const cat = CATEGORIES.find((c) => c.key === activeCat);
    if (cat) runCategory(cat, hood);
  };

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

        {getSessionToken() && userPrefs?.price_tier && (
          <div className="explore-prefs-badge">
            <span className="prefs-badge-icon">✦</span>
            Personalized for you
          </div>
        )}
        {getSessionToken() && userPrefs?.interests?.length > 0 && (
          <div className="explore-prefs-badge">
            <span className="prefs-badge-icon">✦</span>
            Ranked by your interests
          </div>
        )}

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
        </div>

        <div className="events-chip-row">
          <div className="categories-divider" />
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
              Showing {filtered.length} of {results.length} results
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

            <div className={"explore-grid" + (activeCat ? ` grid-cat-${activeCat}` : "")}>
              {filtered.map((p, i) => {
                const ref = placeRef(p);
                const isSaved = ref && savedSlugs.includes(ref);
                return (
                  <a
                    key={ref || `${p.name}-${i}`}
                    className="place-card"
                    href={p.maps_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <div className="place-card-head">
                      <h3>{p.name}</h3>
                      <button
                        type="button"
                        className={"place-save-btn" + (isSaved ? " is-saved" : "")}
                        onClick={(e) => toggleSave(e, p)}
                        aria-label={isSaved ? "Unsave place" : "Save place"}
                      >
                        <Bookmark
                          size={16}
                          fill={isSaved ? "currentColor" : "none"}
                        />
                      </button>
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
                );
              })}
            </div>
          </>
        )}

        {/* ── People also saved ── */}
        {alsoSaved.length > 0 && (
          <section className="also-saved-strip">
            <div className="also-saved-header">
              <h2>
                <Bookmark size={16} strokeWidth={2.3} />
                People also saved
              </h2>
              <p>Collaborative picks based on saved places</p>
            </div>
            <div className="also-saved-scroll">
              {alsoSaved.map((place) => (
                <a
                  key={place.slug}
                  className="also-saved-card"
                  href={`https://www.google.com/maps/search/${encodeURIComponent(place.name)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <h3>{place.name}</h3>
                  {place.category && <span className="place-type">{place.category}</span>}
                  {place.neighborhood && (
                    <p className="place-address">
                      <MapPin size={13} /> {place.neighborhood}
                    </p>
                  )}
                  {place.co_save_count > 0 && (
                    <p className="also-saved-count">
                      Saved by {place.co_save_count} other{place.co_save_count !== 1 ? "s" : ""}
                    </p>
                  )}
                </a>
              ))}
            </div>
          </section>
        )}
      </section>

      {toast && <div className="explore-toast">{toast}</div>}
    </main>
  );
}

export default Explore;