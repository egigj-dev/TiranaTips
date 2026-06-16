import { useState, useEffect, useCallback } from "react";
import "./foryou.css";
import forYouHeroBg from "../../assets/for-you.png";
import Register from "../../components/Authentication/Register";
import Login from "../../components/Authentication/Login";
import loggedSkyline from "../../assets/skyline.png";

import { getPreferences, getSavedPlaces, getSessionToken, getRecommendedPlaces } from "../../lib/api";

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
  Bell,
  Gauge,
  Globe2,
  Pencil,
  LogOut,
  Bookmark,
  X,
  Map,
  MapPin,
  Star,
  Navigation,
  Home,
  BookOpen,
  Camera,
  Laptop,
  BriefcaseBusiness,
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

const prettify = (token) =>
  token.charAt(0).toUpperCase() + token.slice(1).replace(/_/g, " ");

const label = (map, token) => (token ? map[token] || prettify(token) : null);

function ForYou() {
  const [authView, setAuthView] = useState(null);
  const [prefs, setPrefs] = useState(null);
  // Real auth: logged in iff a session token exists. No manual toggle.
  const [isLoggedIn, setIsLoggedIn] = useState(() => !!getSessionToken());

  const refreshPrefs = useCallback(() => {
    setIsLoggedIn(!!getSessionToken());
    getPreferences()
      .then((p) => setPrefs(p))
      .catch((err) => {
        console.error("Failed to load preferences:", err);
      });
  }, []);

  useEffect(() => {
    refreshPrefs();
  }, [refreshPrefs]);

  const handleLogout = async () => {
    const { logout } = await import("../../lib/api");
    await logout();
    setIsLoggedIn(false);
    setPrefs(null);
  };

  return (
    <main className="for-you-page">
      {isLoggedIn ? (
        <LoggedInForYou
          prefs={prefs}
          onLogout={handleLogout}
          onEditPreferences={() => setAuthView("preferences")}
        />
      ) : (
        <GuestForYou
          forYouHeroBg={forYouHeroBg}
          onOpenRegister={() => setAuthView("register")}
          onOpenLogin={() => setAuthView("login")}
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

function GuestForYou({ forYouHeroBg, onOpenRegister, onOpenLogin }) {
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
      text: "Update language, currency, budget, notifications and saved areas anytime.",
    },
  ];

  const modes = [
    {
      icon: Home,
      title: "Local",
      text: "Live like a local",
    },
    {
      icon: BookOpen,
      title: "Student",
      text: "Budget friendly & practical",
    },
    {
      icon: Camera,
      title: "Tourist",
      text: "Discover & explore",
    },
    {
      icon: Laptop,
      title: "Digital Nomad",
      text: "Work, stay & explore",
    },
    {
      icon: BriefcaseBusiness,
      title: "Business Visitor",
      text: "Work trips & meetings",
    },
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

            <button type="button" className="login-btn" onClick={onOpenLogin}>
              Log in
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

function LoggedInForYou({ prefs, onLogout, onEditPreferences }) {
  const [selectedArea, setSelectedArea] = useState(null);
  const [showFullMap, setShowFullMap] = useState(false);
  const [showSavedModal, setShowSavedModal] = useState(false);

  // Real saved places (login-required). Replaces the old hardcoded mock list.
  const [savedPlaces, setSavedPlaces] = useState([]);

  // Recommended places based on user interests (login-required).
  const [recommended, setRecommended] = useState([]);
  const [recommendedLoading, setRecommendedLoading] = useState(false);

  useEffect(() => {
    if (!getSessionToken()) {
      setSavedPlaces([]);
      setRecommended([]);
      return;
    }
    getSavedPlaces()
      .then((r) => setSavedPlaces(r.places || []))
      .catch(() => setSavedPlaces([]));
    // Load interest-based recommendations once prefs are available
    setRecommendedLoading(true);
    import("../../lib/api").then(({ getUserId }) => {
      getRecommendedPlaces(getUserId())
        .then((r) => setRecommended(r.places || []))
        .catch(() => setRecommended([]))
        .finally(() => setRecommendedLoading(false));
    });
  }, []);

  const interests =
    prefs?.interests?.length > 0
      ? prefs.interests.map((i) => label(INTEREST_LABELS, i))
      : [];

  // Real saves carry neighborhood (not "area") and lat/lng. Places with
  // coordinates can appear on the map; the area modal filters by neighborhood.
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

  const summaryItems = [
    {
      icon: WalletCards,
      label: "Budget",
      value: label(TIER_LABELS, prefs?.price_tier) || "Not set",
      className: "summary-budget",
    },
    {
      icon: Coins,
      label: "Currency",
      value: prefs?.currency || "Not set",
      className: "summary-currency",
    },
    {
      icon: Languages,
      label: "Language",
      value: prefs?.language || "Not set",
      className: "summary-language",
    },
    {
      icon: CalendarDays,
      label: "Member since",
      value: memberSince,
      className: "summary-date",
    },
  ];

  // Only the fields that have real backend storage are shown with values; the
  // rest are honestly "Not set" until their models land (areas/style/pace/
  // notifications have no backend yet).
  const preferences = [
    {
      icon: MapPinned,
      label: "Preferred areas",
      value: prefs?.neighborhoods?.length > 0
        ? prefs.neighborhoods.join(", ")
        : "Not set",
    },
    {
      icon: Sparkles,
      label: "City style",
      value: "Not set",
    },
    {
      icon: Bell,
      label: "Notifications",
      value: "Not set",
    },
    {
      icon: Gauge,
      label: "Travel pace",
      value: "Not set",
    },
    {
      icon: Globe2,
      label: "Content language",
      value: prefs?.language ? label({}, prefs.language) : "Not set",
    },
  ];

  const openAreaModal = (area) => {
    setSelectedArea(area);
  };

  const closeAreaModal = () => {
    setSelectedArea(null);
  };

  return (
    <section className="logged-page">
      <section className="logged-hero-dashboard">
        <div className="logged-hero-text">
          <h1>Hello!</h1>
          <p>
            Welcome back to your TiranaTips.
            <br />
            Here’s what’s happening in your city.
          </p>
        </div>

        <img src={loggedSkyline} alt="" className="logged-skyline-image" />

        <div className="logged-hero-actions">
          <button type="button" className="edit-profile-btn" onClick={onEditPreferences}>
            <Pencil size={17} strokeWidth={2.4} />
            Edit profile
          </button>

          <button type="button" className="hero-logout-btn" onClick={onLogout}>
            <LogOut size={17} strokeWidth={2.4} />
            Logout
          </button>
        </div>
      </section>

      <section className="profile-summary-strip">
        <div className="profile-user-mini">
          <div className="profile-avatar">T</div>

          <div>
            <h2>
              Your profile{" "}
              <span>{label(MODE_LABELS, prefs?.mode) || "No mode set"}</span>
            </h2>
          </div>
        </div>

        {summaryItems.map((item) => {
          const Icon = item.icon;

          return (
            <div className={`summary-item ${item.className}`} key={item.label}>
              <span>
                <Icon size={18} strokeWidth={2.2} />
              </span>

              <div>
                <p>{item.label}</p>
                <strong>{item.value}</strong>
              </div>
            </div>
          );
        })}
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
          <div className="recommended-scroll">
            {recommended.map((place) => (
              <a
                key={place.slug}
                className="recommended-card"
                href={`https://www.google.com/maps/search/${encodeURIComponent(place.name)}`}
                target="_blank"
                rel="noreferrer"
              >
                <div className="recommended-card-body">
                  <h3>{place.name}</h3>
                  <p>
                    {place.category}
                    {place.neighborhood ? ` · ${place.neighborhood}` : ""}
                    {place.price_tier ? ` · ${"$".repeat(place.price_tier)}` : ""}
                  </p>
                </div>
                <div className="recommended-card-tags">
                  {(place.interest_tags || []).slice(0, 3).map((tag) => (
                    <span key={tag} className="mini-tag">{tag}</span>
                  ))}
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

      <section className="dashboard-grid">
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
            <p className="saved-empty">
              No saved places yet. Head to Explore and tap the bookmark on any
              place to keep it here.
            </p>
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

        <article className="dashboard-card interests-card">
          <div className="card-title-row">
            <div>
              <h2>Your interests</h2>
              <p>Used to personalize your city tips.</p>
            </div>

            <button type="button">♡</button>
          </div>

          {interests.length === 0 ? (
            <p className="saved-empty">
              No interests selected yet. Edit your profile to choose what you
              like.
            </p>
          ) : (
            <div className="interest-pill-grid">
              {interests.map((interest) => (
                <span key={interest}>{interest}</span>
              ))}
            </div>
          )}

          <button type="button" className="text-link-btn" onClick={onEditPreferences}>
            Edit interests →
          </button>
        </article>

        <article className="dashboard-card preferences-dashboard-card">
          <h2>Your preferences</h2>
          <p>Quick overview of your settings.</p>

          <div className="settings-list">
            {preferences.map((item) => {
              const Icon = item.icon;

              return (
                <div key={item.label}>
                  <span>
                    <Icon size={15} strokeWidth={2.3} />
                  </span>
                  <strong>{item.label}</strong>
                  <p>{item.value}</p>
                  <b>›</b>
                </div>
              );
            })}
          </div>
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

            <button type="button" onClick={() => openAreaModal("Liqeni / Grand Park")}>
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