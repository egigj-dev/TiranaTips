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
  Plane,
  CarFront,
  CalendarRange,
  MessageCircle,
  Compass,
  Leaf,
} from "lucide-react";

import tiranaHeroImage from "../../assets/home.png";
import exchangeNoteImg from "../../assets/home/exchange-note.png";
import airportNoteImg from "../../assets/home/airport-note.png";
import trafficNoteImg from "../../assets/home/traffic-note.png";
import eventsNoteImg from "../../assets/home/events-note.png";

function Home() {
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
      label: "ALL / EUR",
      value: "108.4",
      note: "+0.3%",
      variant: "exchange",
      image: exchangeNoteImg,
    },
    {
      icon: Plane,
      title: "Airport",
      label: "Departures",
      value: "On time",
      note: "",
      variant: "airport",
      image: airportNoteImg,
    },
    {
      icon: CarFront,
      title: "Traffic",
      label: "Busy center",
      value: "2 road closures",
      note: "",
      variant: "traffic",
      image: trafficNoteImg,
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
              <p className="daily-greeting">Good morning,</p>
              <h2>Ready for today?</h2>

              <div className="daily-meta">
                <span>
                  <CalendarDays size={15} strokeWidth={2.2} />
                  Sunday, May 31
                </span>

                <span>
                  <CloudSun size={15} strokeWidth={2.2} />
                  Partly cloudy
                </span>

                <span>
                  <Thermometer size={15} strokeWidth={2.2} />
                  28°C
                </span>
              </div>

              <span className="city-status">
                <i></i>
                Active city
              </span>

              <p className="city-note">Tirana is moving today.</p>
            </div>
          </div>

          <section className="smart-notes-panel">
            <div className="smart-notes-header">
              <h3>Smart Local Notes</h3>
            </div>

            <div className="smart-notes-grid">
              {smartNotes.map((note) => {
                const Icon = note.icon;

                return (
                  <article
                    className={`smart-note-card smart-note-${note.variant}`}
                    key={note.title}
                  >
                    <div className="smart-note-content">
                      <span className="smart-note-icon">
                        <Icon size={19} strokeWidth={2.3} />
                      </span>

                      <h4>{note.title}</h4>
                      <p>{note.label}</p>
                      <strong>{note.value}</strong>

                      {note.note && <small>{note.note}</small>}
                    </div>

                    <img
                      src={note.image}
                      alt=""
                      className="smart-note-illustration"
                      aria-hidden="true"
                    />
                  </article>
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

      <section className="ask-preview-section">
        <div className="ask-preview-left">
          <h2>Ask TiranaTips</h2>
        </div>

        <div className="chat-preview">
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
        </div>

        <div className="try-asking">
          <h3>Try asking</h3>

          <a href="/ask">
            Where should I eat near Blloku? <span>›</span>
          </a>

          <a href="/ask">
            What can I do if it rains? <span>›</span>
          </a>

          <a href="/ask">
            Is Tirana safe at night? <span>›</span>
          </a>

          <a href="/ask">
            Best areas for first-time visitors? <span>›</span>
          </a>
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