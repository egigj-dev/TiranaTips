import { useState } from "react";
import "./foryou.css";
import forYouHeroBg from "../../assets/for-you.png";
import Register from "../../components/Authentication/Register";
import Login from "../../components/Authentication/Login";
import loggedSkyline from "../../assets/skyline.png";

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
} from "lucide-react";

const mapMarkerIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

function ForYou() {
  const [isLoggedIn, setIsLoggedIn] = useState(true);
  const [authView, setAuthView] = useState(null);

  return (
    <main className="for-you-page">
      <div className="preview-toggle">
        <span>Preview:</span>

        <button
          type="button"
          className={!isLoggedIn ? "active" : ""}
          onClick={() => setIsLoggedIn(false)}
        >
          Guest
        </button>

        <button
          type="button"
          className={isLoggedIn ? "active" : ""}
          onClick={() => setIsLoggedIn(true)}
        >
          Logged in
        </button>
      </div>

      {isLoggedIn ? (
        <LoggedInForYou
          onLogout={() => setIsLoggedIn(false)}
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
        />
      )}

      {authView === "preferences" && (
        <Register
          initialStep={2}
          setupOnly={true}
          onClose={() => setAuthView(null)}
          onSwitch={() => setAuthView("login")}
        />
      )}

      {authView === "login" && (
        <Login
          onClose={() => setAuthView(null)}
          onSwitch={() => setAuthView("register")}
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
      icon: "⌂",
      title: "Local",
      text: "Live like a local",
    },
    {
      icon: "▱",
      title: "Student",
      text: "Budget friendly & practical",
    },
    {
      icon: "▣",
      title: "Tourist",
      text: "Discover & explore",
    },
    {
      icon: "▭",
      title: "Digital Nomad",
      text: "Work, stay & explore",
    },
    {
      icon: "▤",
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
            {modes.map((mode) => (
              <button type="button" className="mode-card" key={mode.title}>
                <span>{mode.icon}</span>

                <div>
                  <h3>{mode.title}</h3>
                  <p>{mode.text}</p>
                </div>
              </button>
            ))}
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

function LoggedInForYou({ onLogout, onEditPreferences }) {
  const [selectedArea, setSelectedArea] = useState(null);
  const [showFullMap, setShowFullMap] = useState(false);
  const [showSavedModal, setShowSavedModal] = useState(false);

  const interests = [
    "Coffee",
    "Restaurants",
    "Nature",
    "Culture",
    "Events",
    "Hidden gems",
    "Work-friendly cafés",
    "Day trips",
  ];

  const savedPlaces = [
    {
      name: "Mullixhiu",
      type: "Restaurant",
      area: "Blloku",
      rating: "4.8",
      note: "Great for dinner",
      lat: 41.3186,
      lng: 19.8167,
      image:
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=600&q=80",
    },
    {
      name: "Salt Tirana",
      type: "Café",
      area: "Blloku",
      rating: "4.7",
      note: "Great coffee",
      lat: 41.3211,
      lng: 19.8147,
      image:
        "https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=600&q=80",
    },
    {
      name: "Radio Bar",
      type: "Bar",
      area: "Blloku",
      rating: "4.6",
      note: "Good nightlife",
      lat: 41.3217,
      lng: 19.8153,
      image:
        "https://images.unsplash.com/photo-1572116469696-31de0f17cc34?auto=format&fit=crop&w=600&q=80",
    },
    {
      name: "Pazari i Ri",
      type: "Market",
      area: "Center",
      rating: "4.6",
      note: "Local vibe",
      lat: 41.3295,
      lng: 19.8246,
      image:
        "https://images.unsplash.com/photo-1533900298318-6b8da08a523e?auto=format&fit=crop&w=600&q=80",
    },
    {
      name: "Komiteti",
      type: "Bar",
      area: "Center",
      rating: "4.6",
      note: "Vintage atmosphere",
      lat: 41.3264,
      lng: 19.8205,
      image:
        "https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=600&q=80",
    },
    {
      name: "Liqeni Artificial",
      type: "Nature",
      area: "Liqeni",
      rating: "4.7",
      note: "Relaxing",
      lat: 41.3128,
      lng: 19.8166,
      image:
        "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=600&q=80",
    },
    {
      name: "Grand Park",
      type: "Nature",
      area: "Liqeni",
      rating: "4.8",
      note: "Peaceful walk",
      lat: 41.3147,
      lng: 19.8179,
      image:
        "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=600&q=80",
    },
    {
      name: "Dajti Mountain",
      type: "Nature",
      area: "Dajti",
      rating: "4.7",
      note: "Best views",
      lat: 41.3632,
      lng: 19.9224,
      image:
        "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=600&q=80",
    },
  ];

  const areaSavedPlaces = selectedArea
    ? savedPlaces.filter((place) => place.area === selectedArea)
    : [];

  const summaryItems = [
    {
      icon: WalletCards,
      label: "Budget",
      value: "Mid-range",
      className: "summary-budget",
    },
    {
      icon: Coins,
      label: "Currency",
      value: "EUR / ALL",
      className: "summary-currency",
    },
    {
      icon: Languages,
      label: "Language",
      value: "English",
      className: "summary-language",
    },
    {
      icon: CalendarDays,
      label: "Member since",
      value: "May 2024",
      className: "summary-date",
    },
  ];

  const preferences = [
    {
      icon: MapPinned,
      label: "Preferred areas",
      value: "Blloku, Center, Liqeni",
    },
    {
      icon: Sparkles,
      label: "City style",
      value: "Calm & scenic, Food-focused",
    },
    {
      icon: Bell,
      label: "Notifications",
      value: "On",
    },
    {
      icon: Gauge,
      label: "Travel pace",
      value: "Balanced",
    },
    {
      icon: Globe2,
      label: "Content language",
      value: "English",
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
          <h1>Hello, Sara!</h1>
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
          <div className="profile-avatar">S</div>

          <div>
            <h2>
              Sara Lozi <span>Local</span>
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

            <button
              type="button"
              className="view-all-btn"
              onClick={() => setShowSavedModal(true)}
            >
              View all
            </button>
          </div>

          <div className="saved-dashboard-grid">
            {savedPlaces.slice(0, 5).map((place) => (
              <article className="saved-place-card" key={place.name}>
                <div className="saved-image-wrap">
                  <img src={place.image} alt={place.name} />
                  <button type="button">♡</button>
                </div>

                <div className="saved-place-content">
                  <h3>{place.name}</h3>
                  <p>
                    {place.type} · {place.area}
                  </p>
                  <small>
                    ★ {place.rating} · {place.note}
                  </small>
                </div>
              </article>
            ))}
          </div>
        </article>

        <article className="dashboard-card interests-card">
          <div className="card-title-row">
            <div>
              <h2>Your interests</h2>
              <p>Used to personalize your city tips.</p>
            </div>

            <button type="button">♡</button>
          </div>

          <div className="interest-pill-grid">
            {interests.map((interest) => (
              <span key={interest}>{interest}</span>
            ))}
          </div>

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
              onClick={() => openAreaModal("Center")}
            >
              Center
            </button>

            <button
              type="button"
              className="map-area-chip chip-liqeni"
              onClick={() => openAreaModal("Liqeni")}
            >
              Liqeni
            </button>
          </div>

          <div className="map-preferred-row">
            <span>Preferred areas:</span>

            <button type="button" onClick={() => openAreaModal("Blloku")}>
              Blloku
            </button>

            <i>·</i>

            <button type="button" onClick={() => openAreaModal("Center")}>
              Center
            </button>

            <i>·</i>

            <button type="button" onClick={() => openAreaModal("Liqeni")}>
              Liqeni
            </button>
          </div>

          <button
            type="button"
            className="map-saved-pill"
            onClick={() => openAreaModal("Blloku")}
          >
            <Star size={15} strokeWidth={2.4} />
            <span>Most saved area:</span>
            <strong>Blloku</strong>
          </button>

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
                <article className="saved-modal-card" key={place.name}>
                  <div className="saved-modal-image">
                    <img src={place.image} alt={place.name} />
                    <button type="button">♡</button>
                  </div>

                  <div className="saved-modal-content">
                    <h3>{place.name}</h3>
                    <p>
                      {place.type} · {place.area}
                    </p>
                    <small>
                      ★ {place.rating} · {place.note}
                    </small>
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
                  <article className="saved-modal-card" key={place.name}>
                    <div className="saved-modal-image">
                      <img src={place.image} alt={place.name} />
                      <button type="button">♡</button>
                    </div>

                    <div className="saved-modal-content">
                      <h3>{place.name}</h3>
                      <p>
                        {place.type} · {place.area}
                      </p>
                      <small>
                        ★ {place.rating} · {place.note}
                      </small>
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

                {savedPlaces.map((place) => (
                  <Marker
                    key={place.name}
                    position={[place.lat, place.lng]}
                    icon={mapMarkerIcon}
                  >
                    <Popup>
                      <strong>{place.name}</strong>
                      <br />
                      {place.type} · {place.area}
                      <br />★ {place.rating} · {place.note}
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