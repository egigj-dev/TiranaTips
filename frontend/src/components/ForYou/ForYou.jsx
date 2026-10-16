import { useState, useEffect, useCallback, useRef } from "react";
import "./foryou.css";
import forYouHeroBg from "../../assets/for-you.png";
import Register from "../../components/Authentication/Register";
import Login from "../../components/Authentication/Login";
import loggedSkyline from "../../assets/skyline.png";

import {
  getPreferences,
  deletePreferences,
  getSavedPlaces,
  getSessionToken,
  getRecommendedPlaces,
  getUserProfile,
  updateLanguage,
  setStoredLanguage,
} from "../../lib/api";

import { changePassword, deleteAccount } from "../../lib/auth";

import "leaflet/dist/leaflet.css";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";

import {
  WalletCards,
  Coins,
  Languages,
  CalendarDays,
  MapPinned,
  Sparkles,
  Bookmark,
  X,
  Map,
  MapPin,
  Navigation,
  Home,
  BookOpen,
  Camera,
  Laptop,
  BriefcaseBusiness,
  Pencil,
  ChevronLeft,
  ChevronRight,
  Compass,
  Tag,
} from "lucide-react";

const mapMarkerIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const MODE_LABELS = {
  local: "Local",
  student: "Student",
  tourist: "Tourist",
  nomad: "Digital Nomad",
  business: "Business Visitor",
};

const TIER_LABELS = {
  budget: "Budget-friendly",
  mid: "Mid-range",
  premium: "Premium",
  luxury: "Luxury",
};

const INTEREST_LABELS = {
  live_music: "Live music",
  study_work_cafes: "Study & work cafés",
};

// Concrete UI languages a user can pick for their profile. Mirrors the
// backend's SUPPORTED_LANGUAGES (minus "auto", which is a chat-time detect
// mode, not a stored preference).
const LANGUAGE_OPTIONS = [
  { code: "en", label: "English" },
  { code: "sq", label: "Shqip" },
  { code: "it", label: "Italiano" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "tr", label: "Türkçe" },
  { code: "el", label: "Ελληνικά" },
  { code: "ru", label: "Русский" },
  { code: "zh", label: "中文" },
  { code: "ar", label: "العربية" },
];

const prettify = (token) =>
  token.charAt(0).toUpperCase() + token.slice(1).replace(/_/g, " ");

const label = (map, token) => (token ? map[token] || prettify(token) : null);

function ForYou({ isAuthenticated, onAccountDeleted }) {
  const [authView, setAuthView] = useState(null);
  const [prefs, setPrefs] = useState(null);
  // Account profile (display_name, language). Language lives on the account,
  // NOT in preferences — reading it from prefs is why it showed "Not set".
  const [profile, setProfile] = useState(null);
  // Real auth: logged in iff a session token exists.
  const [isLoggedIn, setIsLoggedIn] = useState(() => !!getSessionToken());

  const refreshPrefs = useCallback(() => {
    const loggedIn = !!getSessionToken();
    setIsLoggedIn(loggedIn);
    if (!loggedIn) {
      setPrefs(null);
      setProfile(null);
      return;
    }
    getPreferences()
      .then(setPrefs)
      .catch((err) => console.error("Failed to load preferences:", err));
    getUserProfile()
      .then(setProfile)
      .catch(() => setProfile(null));
  }, []);

  // Re-sync whenever auth changes app-wide — e.g. logging in/out from the nav
  // bar while already on this page. (Logout now lives only in the nav bar.)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reconcile external localStorage auth when App changes identity.
    refreshPrefs();
  }, [isAuthenticated, refreshPrefs]);

  return (
    <main className="for-you-page">
      {isLoggedIn ? (
        <>
          <LoggedInForYou
            prefs={prefs}
            profile={profile}
            onEditPreferences={() => setAuthView("preferences")}
            onLanguageChanged={refreshPrefs}
          />
          <AccountSettings onReset={refreshPrefs} onDeleted={onAccountDeleted} />
        </>
      ) : (
        <GuestForYou
          forYouHeroBg={forYouHeroBg}
          onOpenRegister={() => setAuthView("register")}
        />
      )}

      {authView === "register" && (
        <Register
          onClose={() => setAuthView(null)}
          onSwitch={() => setAuthView("login")}
          onRegistered={() => setIsLoggedIn(true)}
          onSaved={() => {
            setAuthView(null);
            refreshPrefs();
          }}
        />
      )}

      {authView === "preferences" && (
        <Register
          initialStep={2}
          setupOnly={true}
          onClose={() => setAuthView(null)}
          onSwitch={() => setAuthView("login")}
          onSaved={() => {
            setAuthView(null);
            refreshPrefs();
          }}
        />
      )}

      {authView === "login" && (
        <Login
          onClose={() => setAuthView(null)}
          onLogin={() => {
            setAuthView(null);
            setIsLoggedIn(true);
            refreshPrefs();
          }}
          onSwitchToRegister={() => setAuthView("register")}
        />
      )}
    </main>
  );
}

// Uses form passwords transiently, with busy/message state shared across account actions.
function AccountSettings({ onReset, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  // Uses the confirmation result before deleting stored personalization and refreshing its view.
  const resetPreferences = async () => {
    if (!window.confirm("Reset your preferences?")) return;
    setBusy(true);
    setMessage("");
    try {
      await deletePreferences();
      onReset();
      setMessage("Preferences reset.");
    } catch {
      setMessage("Could not reset preferences. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  // Uses the submitted form's current/new passwords; clears both inputs after success.
  const submitPassword = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setMessage("");
    try {
      await changePassword(data.get("current"), data.get("next"));
      form.reset();
      setMessage("Password changed.");
    } catch {
      setMessage("Could not change password. Check your current password and try again.");
    } finally {
      setBusy(false);
    }
  };

  // Uses the entered password plus explicit confirmation before clearing the account and App state.
  const submitDeletion = async (event) => {
    event.preventDefault();
    if (!window.confirm("Permanently delete your account, saved places and chat history?")) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    try {
      await deleteAccount(data.get("password"));
      await onDeleted();
    } catch {
      setMessage("Could not delete account. Check your password and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="dashboard-card account-settings">
      <h2>Account settings</h2>
      <button type="button" className="edit-profile-btn" disabled={busy} onClick={resetPreferences}>
        Reset preferences
      </button>
      <form onSubmit={submitPassword}>
        <h3>Change password</h3>
        <label htmlFor="current-password">Current password</label>
        <input id="current-password" name="current" type="password" autoComplete="current-password" required maxLength={128} />
        <label htmlFor="new-password">New password</label>
        <input id="new-password" name="next" type="password" autoComplete="new-password" required minLength={6} maxLength={128} />
        <button type="submit" className="edit-profile-btn" disabled={busy}>Change password</button>
      </form>
      <form onSubmit={submitDeletion}>
        <h3>Delete account</h3>
        <label htmlFor="delete-password">Password</label>
        <input id="delete-password" name="password" type="password" autoComplete="current-password" required maxLength={128} />
        <button type="submit" className="edit-profile-btn" disabled={busy}>Delete account</button>
      </form>
      {message && <p role="status">{message}</p>}
    </section>
  );
}

function GuestForYou({ forYouHeroBg, onOpenRegister }) {
  const benefits = [
    {
      icon: "♡",
      title: "Save favorite places",
      text: "Keep restaurants, cafés, viewpoints and useful spots in one personal space.",
    },
    {
      icon: "☆",
      title: "Choose your interests",
      text: "Tell TiranaTips what you like so we can show you what matters most.",
    },
    {
      icon: "♙",
      title: "Set your city mode",
      text: "Local, student, tourist, digital nomad or business visitor — we’ll adapt everything.",
    },
    {
      icon: "⌘",
      title: "Manage preferences",
      text: "Update language, currency, budget and saved areas anytime.",
    },
  ];

  const modes = [
    { icon: Home, title: "Local", text: "Live like a local" },
    { icon: BookOpen, title: "Student", text: "Budget friendly & practical" },
    { icon: Camera, title: "Tourist", text: "Discover & explore" },
    { icon: Laptop, title: "Digital Nomad", text: "Work, stay & explore" },
    { icon: BriefcaseBusiness, title: "Business Visitor", text: "Work trips & meetings" },
  ];

  return (
    <section className="guest-for-you-shell">
      <div className="guest-top">
        <section
          className="guest-hero"
          style={{ backgroundImage: `url(${forYouHeroBg})` }}
        >
          <span className="for-you-pill">For You</span>

          <h1>
            Your personal <br />
            Tirana space.
          </h1>

          <p>
            Create a profile to save places, choose your interests, and get a
            more personal Tirana experience.
          </p>

          <div className="guest-actions">
            <button type="button" className="create-btn" onClick={onOpenRegister}>
              Create account
            </button>
          </div>
        </section>

        <section className="account-benefits">
          <h2>With your account, you can</h2>

          <div className="benefits-grid">
            {benefits.map((benefit) => (
              <article className="benefit-card" key={benefit.title}>
                <div className="benefit-icon">{benefit.icon}</div>

                <div>
                  <h3>{benefit.title}</h3>
                  <p>{benefit.text}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>

      <div className="guest-bottom">
        <section className="mode-section">
          <h2>Choose how you experience Tirana</h2>

          <div className="mode-grid">
            {modes.map((mode) => {
              const Icon = mode.icon;

              return (
                <button type="button" className="mode-card" key={mode.title}>
                  <span className="mode-icon">
                    <Icon size={21} strokeWidth={2.25} />
                  </span>

                  <div>
                    <h3>{mode.title}</h3>
                    <p>{mode.text}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="signup-note">
          <div className="signup-note-icon">✣</div>

          <div>
            <p>
              Once you sign up, your For You page becomes your profile, saved
              places and preference center.
            </p>

            <button
              type="button"
              className="signup-note-link"
              onClick={onOpenRegister}
            >
              Get started and make Tirana yours.
            </button>
          </div>
        </section>
      </div>
    </section>
  );
}

function LoggedInForYou({ prefs, profile, onEditPreferences, onLanguageChanged }) {
  const [selectedArea, setSelectedArea] = useState(null);
  const [showFullMap, setShowFullMap] = useState(false);
  const [showSavedModal, setShowSavedModal] = useState(false);

  const [savedPlaces, setSavedPlaces] = useState([]);
  const [recommended, setRecommended] = useState([]);

  const recScrollRef = useRef(null);
  const [recOverflow, setRecOverflow] = useState(false);

  useEffect(() => {
    if (!getSessionToken()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Discard account data when external auth storage has been cleared.
      setSavedPlaces([]);
      setRecommended([]);
      return;
    }
    getSavedPlaces()
      .then((r) => setSavedPlaces(r.places || []))
      .catch(() => setSavedPlaces([]));
    import("../../lib/api").then(({ getUserId }) => {
      getRecommendedPlaces(getUserId())
        .then((r) => setRecommended(r.places || []))
        .catch(() => setRecommended([]));
    });
  }, []);

  const firstName = (profile?.display_name || "").trim().split(" ")[0];

  // Language is controlled locally for instant feedback, then persisted.
  const [langValue, setLangValue] = useState(profile?.language || "en");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reconcile the language selector with the asynchronously fetched account profile.
    setLangValue(profile?.language || "en");
  }, [profile]);

  const handleLanguageSelect = async (e) => {
    const lang = e.target.value;
    const previous = langValue;
    setLangValue(lang); // optimistic
    try {
      await updateLanguage(lang);
      setStoredLanguage(lang); // so Ask uses the new language immediately
      onLanguageChanged?.();
    } catch (err) {
      console.error("Failed to update language:", err);
      setLangValue(previous);
    }
  };

  const interests =
    prefs?.interests?.length > 0
      ? prefs.interests.map((i) => label(INTEREST_LABELS, i))
      : [];

  const areaSavedPlaces = selectedArea
    ? savedPlaces.filter((place) => place.neighborhood === selectedArea)
    : [];

  const mappablePlaces = savedPlaces.filter(
    (p) => p.lat != null && p.lng != null
  );

  const memberSince = prefs?.created_at
    ? new Date(prefs.created_at).toLocaleDateString("en-GB", {
        month: "short",
        year: "numeric",
      })
    : "—";

  const scrollRecommended = (dir) => {
    if (!recScrollRef.current) return;
    recScrollRef.current.scrollBy({
      left: dir === "left" ? -320 : 320,
      behavior: "smooth",
    });
  };

  // Only surface the scroll chevrons when the rail actually overflows —
  // otherwise they'd sit there doing nothing with just 2–3 recommendations.
  useEffect(() => {
    const el = recScrollRef.current;
    if (!el) return;
    const check = () => setRecOverflow(el.scrollWidth > el.clientWidth + 4);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, [recommended]);

  // Editable, backend-backed preferences only. Notifications / travel pace /
  // city style were removed — no backend to store them. Language has its own
  // inline selector row; these open the edit flow.
  const preferences = [
    {
      icon: WalletCards,
      label: "Budget",
      value: label(TIER_LABELS, prefs?.price_tier) || "Not set",
    },
    {
      icon: Coins,
      label: "Currency",
      value: prefs?.currency || "Not set",
    },
    {
      icon: MapPinned,
      label: "Preferred areas",
      value:
        prefs?.neighborhoods?.length > 0
          ? prefs.neighborhoods.join(", ")
          : "Not set",
    },
  ];

  const openAreaModal = (area) => setSelectedArea(area);
  const closeAreaModal = () => setSelectedArea(null);

  return (
    <section className="logged-page">
      <section className="logged-hero-dashboard">
        <div className="logged-hero-text">
          <h1>Hello{firstName ? `, ${firstName}` : ""}!</h1>
          <p>
            Welcome back to your TiranaTips.
            <br />
            Here’s what’s happening in your city.
          </p>
        </div>

        <img src={loggedSkyline} alt="" className="logged-skyline-image" />

        <div className="logged-hero-actions">
          <button
            type="button"
            className="edit-profile-btn"
            onClick={onEditPreferences}
          >
            <Pencil size={17} strokeWidth={2.4} />
            Edit profile
          </button>
        </div>
      </section>

      {/* Slim identity strip — budget/currency/language moved into the
          Preferences card below, so nothing is double-listed. */}
      <section className="profile-summary-strip slim-strip">
        <div className="profile-user-mini">
          <div className="profile-avatar">
            {(firstName[0] || "T").toUpperCase()}
          </div>

          <div>
            <h2>
              {profile?.display_name || "Your profile"}{" "}
              <span>{label(MODE_LABELS, prefs?.mode) || "No mode set"}</span>
            </h2>
          </div>
        </div>

        <div className="summary-item summary-date">
          <span>
            <CalendarDays size={18} strokeWidth={2.2} />
          </span>
          <div>
            <p>Member since</p>
            <strong>{memberSince}</strong>
          </div>
        </div>
      </section>

      {/* ── Places you'll love ── */}
      {recommended.length > 0 && (
        <section className="recommended-strip">
          <div className="recommended-header">
            <h2>
              <Sparkles size={18} strokeWidth={2.3} />
              Places you&rsquo;ll love
            </h2>
            <p>Based on your interests</p>
          </div>

          <div className="recommended-carousel">
            {recOverflow && (
              <button
                type="button"
                className="rec-side-btn rec-side-left"
                onClick={() => scrollRecommended("left")}
                aria-label="Scroll left"
              >
                <ChevronLeft size={20} strokeWidth={2.5} />
              </button>
            )}

            <div className="recommended-scroll" ref={recScrollRef}>
              {recommended.map((place) => (
                <a
                  key={place.slug}
                  className="recommended-card"
                  href={`https://www.google.com/maps/search/${encodeURIComponent(
                    place.name
                  )}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <div className="recommended-card-body">
                    <h3>{place.name}</h3>
                    <p>
                      {place.category}
                      {place.neighborhood ? ` · ${place.neighborhood}` : ""}
                      {place.price_tier
                        ? ` · ${"$".repeat(place.price_tier)}`
                        : ""}
                    </p>
                  </div>
                  <div className="recommended-card-tags">
                    {(place.interest_tags || []).slice(0, 3).map((tag) => (
                      <span key={tag} className="mini-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </a>
              ))}
            </div>

            {recOverflow && (
              <button
                type="button"
                className="rec-side-btn rec-side-right"
                onClick={() => scrollRecommended("right")}
                aria-label="Scroll right"
              >
                <ChevronRight size={20} strokeWidth={2.5} />
              </button>
            )}
          </div>
        </section>
      )}

      {/* Option B: left column (Saved + Map) is wide; right rail stacks
          Interests + Preferences. No more orphaned half-empty map row. */}
      <section className="dashboard-grid">
        <div className="dashboard-col-main">
          <article className="dashboard-card saved-dashboard-card">
            <div className="card-title-row">
              <div className="dashboard-icon-title compact-title">
                <span>
                  <Bookmark size={20} strokeWidth={2.3} />
                </span>

                <div>
                  <h2>Saved places</h2>
                  <p>Your favorite spots, all in one place.</p>
                </div>
              </div>

              {savedPlaces.length > 0 && (
                <button
                  type="button"
                  className="view-all-btn"
                  onClick={() => setShowSavedModal(true)}
                >
                  View all
                </button>
              )}
            </div>

            {savedPlaces.length === 0 ? (
              <a className="empty-cta empty-cta-saved" href="/explore">
                <span className="empty-cta-icon">
                  <Compass size={22} strokeWidth={2.4} />
                </span>
                <strong>Find places to save</strong>
                <small>Tap the bookmark on any place in Explore.</small>
              </a>
            ) : (
              <div className="saved-dashboard-grid">
                {savedPlaces.slice(0, 5).map((place) => (
                  <article className="saved-place-card" key={place.slug}>
                    <div className="saved-place-content">
                      <h3>{place.name}</h3>
                      <p>
                        {place.category}
                        {place.neighborhood ? ` · ${place.neighborhood}` : ""}
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="dashboard-card personal-map-card">
            <div className="personal-map-header">
              <span>
                <Map size={20} strokeWidth={2.3} />
              </span>

              <div>
                <h2>Your Tirana map</h2>
                <p>Your favorite areas, all in one place.</p>
              </div>
            </div>

            <div className="mini-map-preview real-mini-map">
              <MapContainer
                center={[41.323, 19.819]}
                zoom={13}
                scrollWheelZoom={false}
                dragging={false}
                zoomControl={false}
                attributionControl={false}
                doubleClickZoom={false}
                keyboard={false}
                className="leaflet-mini-map"
              >
                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              </MapContainer>

              <div className="mini-map-soft-overlay"></div>

              <button
                type="button"
                className="map-area-chip chip-blloku"
                onClick={() => openAreaModal("Blloku")}
              >
                Blloku
              </button>

              <button
                type="button"
                className="map-area-chip chip-center"
                onClick={() => openAreaModal("Qendra")}
              >
                Qendra
              </button>

              <button
                type="button"
                className="map-area-chip chip-liqeni"
                onClick={() => openAreaModal("Liqeni / Grand Park")}
              >
                Liqeni
              </button>
            </div>

            <div className="map-preferred-row">
              <span>Browse areas:</span>

              <button type="button" onClick={() => openAreaModal("Blloku")}>
                Blloku
              </button>

              <i>·</i>

              <button type="button" onClick={() => openAreaModal("Qendra")}>
                Qendra
              </button>

              <i>·</i>

              <button
                type="button"
                onClick={() => openAreaModal("Liqeni / Grand Park")}
              >
                Liqeni
              </button>
            </div>

            <button
              type="button"
              className="open-map-btn"
              onClick={() => setShowFullMap(true)}
            >
              <Navigation size={17} strokeWidth={2.4} />
              Open personal map
            </button>
          </article>
        </div>

        <div className="dashboard-col-side">
          <article className="dashboard-card interests-card">
            <div className="card-title-row">
              <div>
                <h2>Your interests</h2>
                <p>Used to personalize your city tips.</p>
              </div>
            </div>

            {interests.length === 0 ? (
              <button
                type="button"
                className="empty-cta empty-cta-interests"
                onClick={onEditPreferences}
              >
                <span className="empty-cta-icon">
                  <Tag size={22} strokeWidth={2.4} />
                </span>
                <strong>Add interests</strong>
                <small>Choose what you like to personalize tips.</small>
              </button>
            ) : (
              <>
                <div className="interest-pill-grid">
                  {interests.map((interest) => (
                    <span key={interest}>{interest}</span>
                  ))}
                </div>

                <button
                  type="button"
                  className="text-link-btn"
                  onClick={onEditPreferences}
                >
                  Edit interests →
                </button>
              </>
            )}
          </article>

          <article className="dashboard-card preferences-dashboard-card">
            <h2>Your preferences</h2>
            <p>Quick overview of your settings.</p>

            <div className="settings-list">
              {preferences.map((item) => {
                const Icon = item.icon;

                return (
                  <button
                    type="button"
                    className="settings-row"
                    key={item.label}
                    onClick={onEditPreferences}
                  >
                    <span>
                      <Icon size={15} strokeWidth={2.3} />
                    </span>
                    <strong>{item.label}</strong>
                    <p>{item.value}</p>
                    <b>›</b>
                  </button>
                );
              })}

              {/* Language — editable inline (account-level, persisted via API) */}
              <div className="settings-row settings-row-lang">
                <span>
                  <Languages size={15} strokeWidth={2.3} />
                </span>
                <strong>Language</strong>
                <select
                  className="lang-select"
                  value={langValue}
                  onChange={handleLanguageSelect}
                  aria-label="Profile language"
                >
                  {LANGUAGE_OPTIONS.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </article>
        </div>
      </section>

      {showSavedModal && (
        <div className="saved-modal-overlay">
          <div className="saved-modal">
            <button
              type="button"
              className="saved-modal-close"
              onClick={() => setShowSavedModal(false)}
            >
              <X size={20} strokeWidth={2.4} />
            </button>

            <div className="saved-modal-header">
              <span>
                <Bookmark size={20} strokeWidth={2.3} />
              </span>

              <div>
                <h2>All saved places</h2>
                <p>Your personal collection of favorite Tirana spots.</p>
              </div>
            </div>

            <div className="saved-modal-grid">
              {savedPlaces.map((place) => (
                <article className="saved-modal-card" key={place.slug}>
                  <div className="saved-modal-content">
                    <h3>{place.name}</h3>
                    <p>
                      {place.category}
                      {place.neighborhood ? ` · ${place.neighborhood}` : ""}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      )}

      {selectedArea && (
        <div className="saved-modal-overlay">
          <div className="saved-modal area-saved-modal">
            <button
              type="button"
              className="saved-modal-close"
              onClick={closeAreaModal}
            >
              <X size={20} strokeWidth={2.4} />
            </button>

            <div className="saved-modal-header">
              <span>
                <MapPin size={20} strokeWidth={2.3} />
              </span>

              <div>
                <h2>Saved places in {selectedArea}</h2>
                <p>Your saved spots around this area.</p>
              </div>
            </div>

            {areaSavedPlaces.length > 0 ? (
              <div className="saved-modal-grid">
                {areaSavedPlaces.map((place) => (
                  <article className="saved-modal-card" key={place.slug}>
                    <div className="saved-modal-content">
                      <h3>{place.name}</h3>
                      <p>
                        {place.category}
                        {place.neighborhood ? ` · ${place.neighborhood}` : ""}
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-saved-area">
                <p>No saved places in this area yet.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {showFullMap && (
        <div className="saved-modal-overlay">
          <div className="personal-map-modal">
            <button
              type="button"
              className="saved-modal-close"
              onClick={() => setShowFullMap(false)}
            >
              <X size={20} strokeWidth={2.4} />
            </button>

            <div className="saved-modal-header">
              <span>
                <Map size={20} strokeWidth={2.3} />
              </span>

              <div>
                <h2>Your personal Tirana map</h2>
                <p>All your saved places and preferred areas.</p>
              </div>
            </div>

            <div className="full-leaflet-map">
              <MapContainer
                center={[41.325, 19.818]}
                zoom={13}
                scrollWheelZoom={true}
                className="leaflet-full-map"
              >
                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                {mappablePlaces.map((place) => (
                  <Marker
                    key={place.slug}
                    position={[place.lat, place.lng]}
                    icon={mapMarkerIcon}
                  >
                    <Popup>
                      <strong>{place.name}</strong>
                      <br />
                      {place.category}
                      {place.neighborhood ? ` · ${place.neighborhood}` : ""}
                    </Popup>
                  </Marker>
                ))}
              </MapContainer>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default ForYou;