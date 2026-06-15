import { useState, useEffect } from "react";
import "./home.css";
import {
  CalendarDays,
  CloudSun,
  Thermometer,
  Users,
  BriefcaseBusiness,
  GraduationCap,
  LaptopMinimal,
  Droplets,
  PlaneTakeoff,
  PlaneLanding,
  MessageCircle,
  Compass,
  Leaf,
  Building2,
  Music,
  Construction,
  BadgePercent,
  Phone,
} from "lucide-react";

import { getCityNotes } from "../../lib/api";

import tiranaHeroImage from "../../assets/home.png";
import exchangeNoteImg from "../../assets/home/exchange-note.png";
import airportNoteImg from "../../assets/home/airport-note.png";

function Home() {
  const [notes, setNotes] = useState(null);

  useEffect(() => {
    const loadCityNotes = () => {
      getCityNotes().then(setNotes).catch(console.error);
    };

    loadCityNotes();

    const interval = setInterval(loadCityNotes, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  const todayLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const formatTime = (isoDate) => {
    if (!isoDate) return "Updating";

    return new Date(isoDate).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const eur = notes?.exchange?.rates?.EUR;

  const shortCity = (city) =>
    city.replace(/\s*\([A-Z]{2}\)\s*$/, "").split(" / ")[0].trim();

  const flightLine = (f) => (f ? `${f.time} · ${shortCity(f.city)}` : null);

  const flightLines = (section) =>
    (section?.flights ?? []).slice(0, 3).map(flightLine).filter(Boolean);

  const dep = flightLines(notes?.departures);
  const arr = flightLines(notes?.arrivals);

  const hour = new Date().getHours();

  const greeting =
    hour < 12 ? "Good morning," : hour < 18 ? "Good afternoon," : "Good evening,";

  const audienceItems = [
    { icon: Users, label: "For locals" },
    { icon: BriefcaseBusiness, label: "Visitors" },
    { icon: GraduationCap, label: "Students" },
    { icon: LaptopMinimal, label: "Digital nomads" },
    { icon: Building2, label: "Business / Investor" },
  ];

  const smartNotes = [
    {
      icon: Phone,
      title: "Emergency",
      label: "Toll-free anywhere",
      lines: notes?.emergency?.numbers?.map(
        (n) => `${n.number} · ${n.label}`
      ) ?? ["112 · General emergency"],
      variant: "emergency",
      href: null,
    },
    {
      icon: Droplets,
      title: "Exchange Rates",
      label: "EUR → ALL · Iliria'98",
      value: eur ? `${eur.buy} / ${eur.sell}` : "—",
      note: eur ? "buy / sell" : "",
      variant: "exchange",
      image: exchangeNoteImg,
      href: "https://iliria98.com/",
    },
    {
      icon: PlaneTakeoff,
      title: "Departures",
      label: "Next from TIA",
      lines: dep,
      variant: "airport",
      image: airportNoteImg,
      href: "https://www.tirana-airport.com/en/flights/departures",
    },
    {
      icon: PlaneLanding,
      title: "Arrivals",
      label: "Next at TIA",
      lines: arr,
      variant: "airport",
      image: airportNoteImg,
      href: "https://www.tirana-airport.com/en/flights/arrivals",
    },
  ];

  const weatherUpdatedTime = formatTime(notes?.weather?.fetched_at);

  const rightNowUpdates = [
    {
      icon: CloudSun,
      category: "Weather",
      title: notes?.weather?.alert_title || "Loading weather update",
      text:
        notes?.weather?.alert_text ||
        "Checking the latest Tirana weather from the backend.",
      time: weatherUpdatedTime,
      variant: "weather",
    },
    {
      icon: Music,
      category: "Events",
      title: "Live music near Skanderbeg Square",
      text: "Performance starts at 9pm.",
      time: "9:00 AM",
      variant: "event",
    },
    {
      icon: Construction,
      category: "Traffic",
      title: "Rruga “Ismail Qemali” partially closed",
      text: "Avoid area until 7pm.",
      time: "7:45 AM",
      variant: "traffic",
    },
    {
      icon: BadgePercent,
      category: "Deals",
      title: "Student museum discount",
      text: "Save on selected museums and culture spots today.",
      time: "10:00 AM",
      variant: "deal",
    },
  ];

  const explorePreview = [
    {
      image:
        "https://images.unsplash.com/photo-1554118811-1e0d58224f24?auto=format&fit=crop&w=900&q=80",
      tag: "Food & Cafés",
      title: "Restaurants, brunch, coffee and work spots.",
      href: "/explore#food-cafes",
    },
    {
      image:
        "https://images.unsplash.com/photo-1564399579883-451a5d44ec08?auto=format&fit=crop&w=900&q=80",
      tag: "Attractions & Culture",
      title: "Museums, landmarks, history and photo spots.",
      href: "/explore#attractions-culture",
    },
    {
      image:
        "https://images.unsplash.com/photo-1521791136064-7986c2920216?auto=format&fit=crop&w=900&q=80",
      tag: "City Guide",
      title: "Weather, exchange, emergency numbers and useful phrases.",
      href: "/explore#city-guide",
    },
    {
      image:
        "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=900&q=80",
      tag: "Day Trips",
      title: "Dajti, Bovilla, Kruja, Berat and more.",
      href: "/explore#day-trips",
    },
  ];

  return (
    <main className="home-page">
      <section className="home-hero">
        <div className="hero-left">
          <div className="hero-leaf-divider">
            <span>
              <Leaf size={18} strokeWidth={2.2} />
            </span>
          </div>

          <h1>
            Discover Tirana <br /> your way.
          </h1>

          <p>
            Plan your day, explore local places, and ask anything about the city
            through a smart guide built for Tirana.
          </p>

          <div className="hero-actions">
            <a href="/ask" className="primary-btn">
              <span>
                <MessageCircle size={18} strokeWidth={2.4} />
              </span>
              Ask TiranaTips
            </a>

            <a href="/explore" className="secondary-btn">
              <span>
                <Compass size={18} strokeWidth={2.4} />
              </span>
              Explore the city
            </a>
          </div>

          <div className="hero-audience">
            {audienceItems.map((item) => {
              const Icon = item.icon;

              return (
                <span key={item.label}>
                  <i>
                    <Icon size={14} strokeWidth={2.3} />
                  </i>
                  {item.label}
                </span>
              );
            })}
          </div>
        </div>

        <div className="hero-right">
          <div className="daily-card">
            <img
              src={tiranaHeroImage}
              alt="Illustrated Tirana skyline"
              className="daily-hero-image"
            />

            <div className="daily-card-content">
              <p className="daily-greeting">{greeting}</p>
              <h2>Ready for today?</h2>

              <div className="daily-meta">
                <span>
                  <CalendarDays size={15} strokeWidth={2.2} />
                  {todayLabel}
                </span>

                <span>
                  <CloudSun size={15} strokeWidth={2.2} />
                  {notes?.weather?.label ?? "—"}
                </span>

                <span>
                  <Thermometer size={15} strokeWidth={2.2} />
                  {notes?.weather ? `${notes.weather.temp_c}°C` : "—"}
                </span>
              </div>

              <p className="city-note">
                {notes?.weather?.alert_text || "Have a great day in Tirana."}
              </p>
            </div>
          </div>

          <section className="smart-notes-panel">
            <div className="smart-notes-header">
              <h3>Smart Local Notes</h3>
            </div>

            <div className="smart-notes-grid">
              {smartNotes.map((note) => {
                const Icon = note.icon;
                const Card = note.href ? "a" : "article";

                const linkProps = note.href
                  ? {
                    href: note.href,
                    target: "_blank",
                    rel: "noreferrer",
                    style: {
                      color: "inherit",
                      textDecoration: "none",
                      cursor: "pointer",
                    },
                  }
                  : {};

                return (
                  <Card
                    className={`smart-note-card smart-note-${note.variant}`}
                    key={note.title}
                    {...linkProps}
                  >
                    <div className="smart-note-content">
                      <span className="smart-note-icon">
                        <Icon size={19} strokeWidth={2.3} />
                      </span>

                      <h4>{note.title}</h4>
                      <p>{note.label}</p>

                      {note.lines ? (
                        note.lines.length ? (
                          note.lines.map((line) => (
                            <strong
                              key={line}
                              style={{
                                display: "block",
                                fontSize: "0.82em",
                                whiteSpace: "nowrap",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                              }}
                            >
                              {line}
                            </strong>
                          ))
                        ) : (
                          <strong>—</strong>
                        )
                      ) : (
                        <>
                          <strong>{note.value}</strong>
                          {note.note && <small>{note.note}</small>}
                        </>
                      )}
                    </div>

                    {note.image && (
                      <img
                        src={note.image}
                        alt=""
                        className="smart-note-illustration"
                        aria-hidden="true"
                      />
                    )}
                  </Card>
                );
              })}
            </div>
          </section>
        </div>
      </section>

      <section className="right-now-section">
        <div className="section-heading-row">
          <div>
            <h2>Right now in Tirana</h2>
            <p>
              <span className="live-dot"></span>
              Live updates from today
            </p>
          </div>

          <a href="/explore">See all updates →</a>
        </div>

        <div className="right-now-grid">
          {rightNowUpdates.map((item) => {
            const Icon = item.icon;

            return (
              <article
                className={`right-now-card right-now-${item.variant}`}
                key={item.title}
              >
                <span className="right-now-icon">
                  <Icon size={21} strokeWidth={2.3} />
                </span>

                <div className="right-now-content">
                  <span className="right-now-category">{item.category}</span>
                  <h3>{item.title}</h3>
                  <p>{item.text}</p>
                  <small>Updated {item.time}</small>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="explore-preview-section">
        <div className="explore-preview-intro">
          <h2>Start exploring Tirana</h2>

          <p>
            Browse food, attractions, events, transport, city guide, day trips
            and deals from one place.
          </p>

          <a href="/explore" className="explore-preview-link">
            Open Explore <span>→</span>
          </a>
        </div>

        <div className="explore-preview-grid">
          {explorePreview.map((item) => (
            <a className="explore-preview-card" href={item.href} key={item.tag}>
              <img src={item.image} alt={item.tag} />

              <div className="explore-preview-card-content">
                <h3>{item.tag}</h3>
                <p>{item.title}</p>
                <span>→</span>
              </div>
            </a>
          ))}
        </div>
      </section>
    </main>
  );
}

export default Home;