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
  CalendarRange,
  MessageCircle,
  Compass,
  Leaf,
} from "lucide-react";

import { getCityNotes } from "../../lib/api";

import tiranaHeroImage from "../../assets/home.png";
import exchangeNoteImg from "../../assets/home/exchange-note.png";
import airportNoteImg from "../../assets/home/airport-note.png";
import eventsNoteImg from "../../assets/home/events-note.png";

// Tirana's international recognition — hardcoded editorial content. Slow-
// changing (a few entries a year), so a committed list is the right amount of
// engineering; each links to its primary source.
const ACHIEVEMENTS = [
  {
    year: "2018",
    title: "European Prize for Urban Public Space",
    blurb:
      "Skanderbeg Square won Europe's top public-space award, beating 279 candidates from 32 countries for its pedestrian-first redesign.",
    href: "https://ruby-press.com/skanderbeg-square-by-51n4e-and-anri-sala-wins-european-prize-for-urban-public-space/",
  },
  {
    year: "2022",
    title: "European Youth Capital",
    blurb:
      "Awarded the year-long title by the European Youth Forum, running 100+ events under the slogan \u201cActivate Youth.\u201d",
    href: "https://www.youthforum.org/news/congratulations-tirana-winner-of-the-european-youth-capital-for-2022",
  },
  {
    year: "2023",
    title: "The Pyramid Reborn",
    blurb:
      "MVRDV transformed the communist-era Pyramid into a public creative hub, home to the TUMO Center for free tech education.",
    href: "https://www.mvrdv.com/projects/312/the-pyramid-of-tirana",
  },
  {
    year: "2024",
    title: "Lonely Planet Spotlight",
    blurb:
      "Featured in Lonely Planet's global travel guides, introducing Tirana to mainstream travelers as a dynamic European destination.",
    href: "https://www.lonelyplanet.com/",
  },
  {
    year: "2024",
    title: "Capital of Innovation Award",
    blurb:
      "Honored at the ANGI Awards in Rome for e-governance, smart infrastructure, and grassroots tech support.",
    href: "https://www.giovaniinnovatori.it/",
  },
  {
    year: "2025",
    title: "Startup Ecosystem Growth",
    blurb:
      "Recorded +40.5% annual growth (StartupBlink), ranking as the 32nd strongest startup environment in Eastern Europe.",
    href: "https://www.startupblink.com/startup-ecosystem/tirana-al",
  },
];

function Home() {
  // Live data for the hero + Smart Local Notes. null until the backend's
  // first refresh completes — cards render "—" placeholders meanwhile.
  const [notes, setNotes] = useState(null);

  useEffect(() => {
    getCityNotes().then(setNotes).catch(console.error);
  }, []);

  // Real date, formatted like the old mock ("Sunday, May 31").
  const todayLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const eur = notes?.exchange?.rates?.EUR;
  // "Basel-Mulhouse-Freiburg (FR)" / "Athens / Athine (GR)" → "Basel-Mulhouse-Freiburg",
  // "Athens" — cards have no room for country codes and bilingual aliases.
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
  ];

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

  const rightNowUpdates = [
    {
      icon: "🌧️",
      title: "Rain expected after 5pm",
      text: "Best to carry an umbrella.",
      time: "8:30 AM",
    },
    {
      icon: "🎵",
      title: "Live music near Skanderbeg Square",
      text: "Performance starts at 9pm.",
      time: "9:00 AM",
    },
    {
      icon: "🚧",
      title: "Rruga “Ismail Qemali” partially closed",
      text: "Avoid area until 7pm.",
      time: "7:45 AM",
    },
    {
      icon: "🍸",
      title: "Jazz at Radio Bar",
      text: "Live set tonight, cozy vibe.",
      time: "10:00 AM",
    },
  ];

  const cityLens = [
    {
      image:
        "https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=900&q=80",
      tag: "Local Favorites",
      title: "Hidden spots loved by locals.",
    },
    {
      image:
        "https://images.unsplash.com/photo-1587974928442-77dc3e0dba72?auto=format&fit=crop&w=900&q=80",
      tag: "First Time in Tirana",
      title: "Must-see places & easy wins.",
    },
    {
      image:
        "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=900&q=80",
      tag: "Slow & Scenic",
      title: "Nature, walks & peaceful corners.",
    },
  ];

  const globalCards = [
    {
      icon: "🌍",
      title: "For Visitors",
      text: "Top attractions, local tips, and things you’ll love.",
    },
    {
      icon: "🎓",
      title: "For Students",
      text: "A growing city with culture, uni vibes, and affordable daily life.",
    },
    {
      icon: "💻",
      title: "For Digital Nomads",
      text: "Why Tirana is becoming a remote work hub.",
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
                {notes?.weather?.forecast || "Have a great day in Tirana."}
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
                // Cards with a source link render as <a> so they're real,
                // accessible links (middle-click, keyboard, SEO) — style
                // overrides keep them visually identical to the <article>s.
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
          {rightNowUpdates.map((item) => (
            <article className="right-now-card" key={item.title}>
              <span className="right-now-icon">{item.icon}</span>

              <div>
                <h3>{item.title}</h3>
                <p>{item.text}</p>
                <small>{item.time}</small>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="achievements-section">
        <div className="achievements-intro">
          <h2>Why the world is talking about Tirana</h2>
          <p>Recent international recognition for the city.</p>
        </div>

        <div className="achievements-grid">
          {ACHIEVEMENTS.map((a) => (
            <a
              className="achievement-card"
              key={a.year + a.title}
              href={a.href}
              target="_blank"
              rel="noreferrer"
            >
              <span className="achievement-year">{a.year}</span>
              <h3>{a.title}</h3>
              <p>{a.blurb}</p>
              <span className="achievement-more">Read more →</span>
            </a>
          ))}
        </div>
      </section>

      <section className="city-lens-section">
        <div className="city-lens-intro">
          <h2>Choose your city lens</h2>

          <div className="lens-tabs">
            <button className="active">Local</button>
            <button>First Visit</button>
            <button>Student Life</button>
            <button>Calm Day</button>
          </div>
        </div>

        <div className="city-lens-grid">
          {cityLens.map((item) => (
            <article className="lens-card" key={item.tag}>
              <img src={item.image} alt={item.tag} />

              <div className="lens-card-content">
                <h3>{item.tag}</h3>
                <p>{item.title}</p>
                <span>→</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="global-preview-section">
        <h2>Tirana, seen globally.</h2>

        <div className="global-preview-grid">
          {globalCards.map((card) => (
            <article className="global-card" key={card.title}>
              <span>{card.icon}</span>
              <h3>{card.title}</h3>
              <p>{card.text}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

export default Home;