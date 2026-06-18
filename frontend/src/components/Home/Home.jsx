import { useEffect, useRef, useState } from "react";
import "./home.css";

import {
  CalendarDays,
  CloudSun,
  Thermometer,
  MessageCircle,
  Compass,
  Construction,
  Music,
  Utensils,
  Landmark,
  Map,
  Mountain,
  Users,
  BriefcaseBusiness,
  GraduationCap,
  LaptopMinimal,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { getCityNotes, getNews, getPreferences } from "../../lib/api";

import tiranaHeroImage from "../../assets/home.png";

function Home() {
  const [notes, setNotes] = useState(null);
  const [news, setNews] = useState([]);
  const [userPrefs, setUserPrefs] = useState(null);

  const newsScrollRef = useRef(null);
  const isDraggingRef = useRef(false);
  const startXRef = useRef(0);
  const scrollLeftRef = useRef(0);
  const hasDraggedRef = useRef(false);

  useEffect(() => {
    const loadCityNotes = () => {
      getCityNotes().then(setNotes).catch(console.error);
    };

    const loadNews = () => {
      getNews().then(setNews).catch(console.error);
    };

    const loadPrefs = () => {
      getPreferences()
        .then(setUserPrefs)
        .catch(() => {});
    };

    loadCityNotes();
    loadNews();
    loadPrefs();

    const interval = setInterval(() => {
      loadCityNotes();
      loadNews();
    }, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  const scrollNews = (direction) => {
    if (!newsScrollRef.current) return;

    newsScrollRef.current.scrollBy({
      left: direction === "left" ? -380 : 380,
      behavior: "smooth",
    });
  };

  const handleNewsPointerDown = (e) => {
    if (!newsScrollRef.current) return;

    isDraggingRef.current = true;
    hasDraggedRef.current = false;

    newsScrollRef.current.classList.add("is-dragging");

    startXRef.current = e.pageX - newsScrollRef.current.offsetLeft;
    scrollLeftRef.current = newsScrollRef.current.scrollLeft;
  };

  const handleNewsPointerMove = (e) => {
    if (!isDraggingRef.current || !newsScrollRef.current) return;

    const x = e.pageX - newsScrollRef.current.offsetLeft;
    const walk = (x - startXRef.current) * 1.4;

    if (Math.abs(walk) > 6) {
      hasDraggedRef.current = true;
    }

    newsScrollRef.current.scrollLeft = scrollLeftRef.current - walk;
  };

  const stopNewsDrag = () => {
    isDraggingRef.current = false;
    hasDraggedRef.current = false;

    if (newsScrollRef.current) {
      newsScrollRef.current.classList.remove("is-dragging");
    }
  };

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

  // User's preferred currency from their profile, or fall back to EUR
  const preferredCurrency =
    userPrefs?.currency && userPrefs.currency !== "ALL"
      ? userPrefs.currency
      : "EUR";

  const userRate = notes?.exchange?.rates?.[preferredCurrency];

  const eur = notes?.exchange?.rates?.EUR;

  // Currency code → symbol map for the exchange rate icon
  const currencySymbols = {
    EUR: "\u20AC", USD: "$", GBP: "\u00A3", CHF: "Fr.",
    TRY: "\u20BA", CAD: "CA$", AUD: "A$",
  };
  const currencySymbol = currencySymbols[preferredCurrency] || preferredCurrency;

  const weatherUpdatedTime = formatTime(notes?.weather?.fetched_at);

  const weatherLabel = notes?.weather?.label ?? "Overcast";

  const weatherTempValue = notes?.weather?.temp_c ?? 30;
  const weatherTemp = `${weatherTempValue}°C`;

  const weatherNote =
    notes?.weather?.alert_text || `Currently around ${weatherTemp}.`;

  const weekday = todayLabel.split(",")[0];
  const dateWithoutWeekday = todayLabel.replace(`${weekday}, `, "");

  const rightNowUpdates = [
    {
      icon: CloudSun,
      category: "Weather",
      title: notes?.weather?.alert_title || "Overcast in Tirana",
      text: notes?.weather?.alert_text || `Currently around ${weatherTemp}.`,
      time: weatherUpdatedTime,
      variant: "weather",
    },
    {
      icon: Music,
      category: "Events",
      title: "Live music near Skanderbeg Square",
      text: "Performance starts at 9pm.",
      time: "09:00",
      variant: "event",
    },
    {
      icon: Construction,
      category: "Traffic",
      title: "Rruga “Ismail Qemali” partially closed",
      text: "Avoid area until 7pm.",
      time: "07:45",
      variant: "traffic",
    },
  ];

  const explorePreview = [
    {
      icon: Utensils,
      image:
        "https://images.unsplash.com/photo-1554118811-1e0d58224f24?auto=format&fit=crop&w=900&q=80",
      title: "Food & Cafés",
      text: "Restaurants, brunch, coffee and work spots.",
      href: "/explore#food-cafes",
    },
    {
      icon: Landmark,
      image:
        "https://images.unsplash.com/photo-1564399579883-451a5d44ec08?auto=format&fit=crop&w=900&q=80",
      title: "Attractions & Culture",
      text: "Museums, landmarks, history and photo spots.",
      href: "/explore#attractions-culture",
    },
    {
      icon: Map,
      image:
        "https://images.unsplash.com/photo-1524231757912-21f4fe3a7200?auto=format&fit=crop&w=900&q=80",
      title: "City Guide",
      text: "Weather, exchange, useful numbers and local tips.",
      href: "/explore#city-guide",
    },
    {
      icon: Mountain,
      image:
        "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=900&q=80",
      title: "Day Trips",
      text: "Dajti, Bovilla, Kruja, Berat and more.",
      href: "/explore#day-trips",
    },
  ];

  const audienceItems = [
    {
      icon: Users,
      label: "Locals",
      text: "Living in Tirana",
    },
    {
      icon: BriefcaseBusiness,
      label: "Visitors",
      text: "Exploring the city",
    },
    {
      icon: GraduationCap,
      label: "Students",
      text: "Studying in Tirana",
    },
    {
      icon: LaptopMinimal,
      label: "Digital Nomads",
      text: "Working from anywhere",
    },
  ];

  return (
    <main className="home-page">
      <section className="home-hero">
        <div className="hero-bg">
          <img
            src={tiranaHeroImage}
            alt="Tirana city view"
            className="hero-bg-image"
          />
        </div>

        <div className="hero-content">
          <h1>
            Discover Tirana <br /> your way.
          </h1>

          <p className="hero-description">
            Plan your day, explore local places, and ask anything about the city
            through a smart guide built for Tirana.
          </p>

          <div className="hero-actions">
            <a href="/ask" className="primary-btn">
              <MessageCircle size={18} strokeWidth={2.4} />
              Ask TiranaTips
            </a>

            <a href="/explore" className="secondary-btn">
              <Compass size={18} strokeWidth={2.4} />
              Explore the city
            </a>
          </div>

          <div className="hero-info-bar">
            <div className="hero-info-item hero-weather-block">
              <div className="hero-weather-top">
                <span>
                  <CloudSun size={18} strokeWidth={2.2} />
                  {weatherLabel}
                </span>

                <i />

                <span>
                  <Thermometer size={17} strokeWidth={2.2} />
                  {weatherTemp}
                </span>
              </div>

              <p>{weatherNote}</p>
            </div>

            <a
              className="hero-info-item hero-exchange-block"
              href="https://iliria98.com/"
              target="_blank"
              rel="noreferrer"
              aria-label="Open Iliria 98 exchange rates"
            >
              <span className="currency-symbol-icon">{currencySymbol}</span>

              <div>
                <strong>{preferredCurrency} → ALL</strong>
                <small>{userRate ? `${userRate.buy} / ${userRate.sell}` : eur ? `${eur.buy} / ${eur.sell}` : "94.5 / 95.2"}</small>
              </div>
            </a>

            <div className="hero-info-item hero-date-block">
              <CalendarDays size={25} strokeWidth={2.1} />

              <div>
                <strong>{weekday}</strong>
                <small>{dateWithoutWeekday}</small>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* <section className="right-now-section">
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
                  <Icon size={22} strokeWidth={2.3} />
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
      </section> */}

      <section className="news-section">
        <div className="section-heading-row">
          <div>
            <h2>News in Albania</h2>
            <p>Headlines from local English-language sources</p>
          </div>

          <a href="https://www.tiranatimes.com/" target="_blank" rel="noreferrer">
            See all news →
          </a>
        </div>

        <div className="news-carousel-wrap">
          <button
            type="button"
            className="news-side-btn news-side-btn-left"
            onClick={() => scrollNews("left")}
            aria-label="Scroll news left"
          >
            <ChevronLeft size={22} strokeWidth={2.5} />
          </button>

          <div
            className="news-scroll-container"
            ref={newsScrollRef}
            onPointerDown={handleNewsPointerDown}
            onPointerMove={handleNewsPointerMove}
            onPointerUp={stopNewsDrag}
            onPointerLeave={stopNewsDrag}
            onPointerCancel={stopNewsDrag}
          >
            <div className="news-scroll-track">
              {news.length === 0 && (
                <p className="news-empty">Loading headlines…</p>
              )}

              {news.map((item, i) => {
                const sourceName =
                  {
                    tiranatimes: "Tirana Times",
                    exit: "Exit.al",
                    adn: "Albanian Daily News",
                  }[item.source] || item.source;

                return (
                  <a
                    className="news-card"
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    key={`${item.source}-${i}`}
                    draggable="false"
                  >
                    {item.image_url && (
                      <div className="news-card-img">
                        <img
                          src={item.image_url}
                          alt={item.title}
                          loading="lazy"
                          draggable="false"
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
                          }}
                        />
                      </div>
                    )}

                    <div className="news-card-body">
                      <span className="news-card-source">{sourceName}</span>
                      <h3>{item.title}</h3>
                    </div>
                  </a>
                );
              })}
            </div>
          </div>

          <button
            type="button"
            className="news-side-btn news-side-btn-right"
            onClick={() => scrollNews("right")}
            aria-label="Scroll news right"
          >
            <ChevronRight size={22} strokeWidth={2.5} />
          </button>
        </div>
      </section>

      <section className="explore-preview-section">
        <div className="section-heading-row explore-heading">
          <div>
            <h2>Start exploring Tirana</h2>
            <p>Choose where to start, then go deeper in Explore.</p>
          </div>

          <a href="/explore">Open Explore →</a>
        </div>

        <div className="explore-preview-grid">
          {explorePreview.map((item) => {
            const Icon = item.icon;

            return (
              <a
                className="explore-preview-card"
                href={item.href}
                key={item.title}
              >
                <img src={item.image} alt={item.title} />

                <div className="explore-icon">
                  <Icon size={22} strokeWidth={2.2} />
                </div>

                <div className="explore-preview-card-content">
                  <h3>{item.title}</h3>
                  <p>{item.text}</p>
                  <span>Explore →</span>
                </div>
              </a>
            );
          })}
        </div>
      </section>
    </main>
  );
}

export default Home;