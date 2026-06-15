import { useState, useEffect } from "react";
import "./home.css";
import {
  CalendarDays,
  CloudSun,
  Thermometer,
  Droplets,
  PlaneTakeoff,
  PlaneLanding,
  CalendarRange,
  MessageCircle,
  Compass,
  Leaf,
  Music,
  Construction,
  BadgePercent,
  Landmark,
} from "lucide-react";

import { getCityNotes } from "../../lib/api";

import tiranaHeroImage from "../../assets/home.png";
import exchangeNoteImg from "../../assets/home/exchange-note.png";
import airportNoteImg from "../../assets/home/airport-note.png";
import eventsNoteImg from "../../assets/home/events-note.png";

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

  const smartNotes = [
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
    {
      icon: CalendarRange,
      title: "Events Tonight",
      label: "Live & local",
      value: "3 tonight",
      note: "",
      variant: "events",
      image: eventsNoteImg,
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

  const globalCards = [
    {
      icon: "📰",
      title: "Tirana in the press",
      text: "Global articles, travel features, and international media mentions about Tirana.",
      meta: "Media · Newspapers · Travel magazines",
    },
    {
      icon: "📍",
      title: "Travel creator picks",
      text: "Places mentioned by bloggers, YouTubers, TikTokers, and travel creators.",
      meta: "Blogs · Reels · YouTube",
    },
    {
      icon: "💬",
      title: "Nomad & student notes",
      text: "What foreigners say about living, studying, working, and exploring the city.",
      meta: "Nomads · Students · Expats",
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

              <span className="city-status">
                <i></i>
                Active city
              </span>

              <p className="city-note">
                {notes?.weather?.alert_text || "Tirana is moving today."}
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

                    <img
                      src={note.image}
                      alt=""
                      className="smart-note-illustration"
                      aria-hidden="true"
                    />
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

      <section className="tirana-glance-section">
        <div className="tirana-glance-icon">
          <Landmark size={24} strokeWidth={2.2} />
        </div>

        <div className="tirana-glance-content">
          <span>Tirana at a glance</span>

          <h2>A city with many layers.</h2>

          <div className="tirana-glance-text-grid">
            <p>
              Tirana’s area has been inhabited since ancient times, with archaeological
              traces from Illyrian, Roman, and Byzantine periods. These early layers
              give the city a longer history than its modern capital identity.
            </p>

            <p>
              Tirana began to take shape as an urban center in the early 17th century,
              when Sulejman Pasha Bargjini founded key landmarks such as a mosque, a
              bakery, and a hammam, helping define the city’s early core.
            </p>

            <p>
              In 1920, Tirana became the capital of Albania. Today, it blends historic
              neighborhoods, communist-era architecture, colorful facades, café
              culture, and a young creative rhythm.
            </p>
          </div>
        </div>
      </section>

      <section className="ask-preview-section">
        <div className="ask-preview-left">
          <span className="ask-preview-pill">AI local assistant</span>

          <h2>Ask TiranaTips</h2>

          <p>
            Need a quick local answer? Ask about food, weather plans, safety,
            transport, nightlife, or what to do today.
          </p>

          <a href="/ask" className="ask-preview-btn">
            Open Ask Tirana <span>→</span>
          </a>
        </div>

        <a href="/ask" className="chat-preview" aria-label="Open Ask Tirana">
          <div className="chat-bubble user-bubble">
            What can I do in Tirana today if I want something calm?
            <small>10:30 AM</small>
          </div>

          <div className="chat-answer">
            <div className="chat-bubble ai-bubble">
              <strong>TiranaTips</strong>
              Start with coffee near Blloku, take a walk around the lake, then
              end with dinner somewhere cozy and local.
              <small>10:31 AM</small>
            </div>
          </div>
        </a>
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

      <section className="global-preview-section">
        <div className="global-preview-header">
          <div>
            <h2>Tirana, seen globally.</h2>
            <p>
              International articles, travel guides, creators and media mentions
              shaping how the world sees Tirana.
            </p>
          </div>
        </div>

        <div className="global-preview-grid">
          {globalCards.map((card) => (
            <a href="/global" className="global-card" key={card.title}>
              <span>{card.icon}</span>

              <div>
                <h3>{card.title}</h3>
                <p>{card.text}</p>
                <small>{card.meta}</small>
              </div>

              <b>→</b>
            </a>
          ))}
        </div>
      </section>
    </main>
  );
}

export default Home;