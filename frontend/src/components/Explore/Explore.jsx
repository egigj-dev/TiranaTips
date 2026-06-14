import "./explore.css";
import {
  Search,
  SlidersHorizontal,
  Utensils,
  Landmark,
  CalendarDays,
  BusFront,
  Info,
  Mountain,
  BadgePercent,
  Star,
  Bookmark,
  Heart,
  Navigation,
  ArrowRight,
  Coffee,
  Camera,
  Leaf,
  Music,
  ShoppingBag,
  Plane,
  CarTaxiFront,
  ParkingCircle,
  Footprints,
  Bike,
  Sun,
  Coins,
  Phone,
  Languages,
  ShieldCheck,
  MapPin,
} from "lucide-react";

const shortcutCards = [
  {
    icon: Utensils,
    title: "Food & Cafés",
    text: "Restaurants, brunch, coffee",
    href: "#food-cafes",
  },
  {
    icon: Landmark,
    title: "Attractions & Culture",
    text: "Museums, history, landmarks",
    href: "#attractions-culture",
  },
  {
    icon: CalendarDays,
    title: "Events",
    text: "Tonight, weekend, free",
    href: "#events",
  },
  {
    icon: BusFront,
    title: "Transport",
    text: "Airport, taxis, buses",
    href: "#transport",
  },
  {
    icon: Info,
    title: "City Guide",
    text: "Weather, exchange, help",
    href: "#city-guide",
  },
  {
    icon: Mountain,
    title: "Day Trips",
    text: "Dajti, Bovilla, Kruja",
    href: "#day-trips",
  },
  {
    icon: BadgePercent,
    title: "Deals",
    text: "Food, tickets, shopping",
    href: "#deals",
  },
];

const pickedForYou = [
  {
    tag: "Budget cafés near Blloku",
    image:
      "https://images.unsplash.com/photo-1554118811-1e0d58224f24?auto=format&fit=crop&w=900&q=80",
    title: "Oda Café",
    meta: "Café · Blloku",
    text: "Great coffee, calm vibe, student friendly.",
    price: "€ · Budget",
  },
  {
    tag: "Free events this week",
    image:
      "https://images.unsplash.com/photo-1501386761578-eac5c94b800a?auto=format&fit=crop&w=900&q=80",
    title: "Jazz at Radio Bar",
    meta: "Today · 21:00",
    text: "Live jazz night in a cozy atmosphere.",
    price: "Free",
  },
  {
    tag: "Attractions near saved places",
    image:
      "https://images.unsplash.com/photo-1564399579883-451a5d44ec08?auto=format&fit=crop&w=900&q=80",
    title: "Bunk’Art 2",
    meta: "Museum · Center",
    text: "History, culture, and student discounts.",
    price: "€€ · Affordable",
  },
  {
    tag: "Near your saved places",
    image:
      "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=900&q=80",
    title: "Liqeni i Tiranës",
    meta: "Park · Near you",
    text: "Perfect for a walk or study break.",
    price: "Free",
  },
];

const trendingPlaces = [
  {
    image:
      "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=900&q=80",
    title: "Salt Tirana",
    meta: "Café · Blloku",
    text: "Popular for brunch and social dinners.",
    price: "€€ · Mid-range",
  },
  {
    image:
      "https://images.unsplash.com/photo-1533900298318-6b8da08a523e?auto=format&fit=crop&w=900&q=80",
    title: "Pazari i Ri",
    meta: "Food · Culture · Center",
    text: "Local food, market vibes and culture.",
    price: "€ · Budget",
  },
  {
    image:
      "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=900&q=80",
    title: "Mullixhiu",
    meta: "Restaurant · Liqeni",
    text: "Modern Albanian cuisine in a beautiful setting.",
    price: "€€€ · Premium",
  },
];

const events = [
  {
    day: "17",
    month: "MAY",
    weekday: "SAT",
    title: "Tirana Jazz Night",
    time: "21:00 · Tonight",
    location: "Radio Bar, Blloku",
    type: "Music",
    price: "€10",
    image:
      "https://images.unsplash.com/photo-1511192336575-5a79af67a629?auto=format&fit=crop&w=400&q=80",
  },
  {
    day: "18",
    month: "MAY",
    weekday: "SUN",
    title: "Art in the Park",
    time: "11:00 · This weekend",
    location: "Grand Park",
    type: "Art",
    price: "Free",
    image:
      "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=400&q=80",
  },
  {
    day: "19",
    month: "MAY",
    weekday: "MON",
    title: "Street Food Festival",
    time: "12:00 · This weekend",
    location: "Pazari i Ri",
    type: "Food",
    price: "Free",
    image:
      "https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=400&q=80",
  },
];

const placeCategories = [
  {
    icon: Utensils,
    title: "Restaurants",
    text: "Traditional, modern, casual",
  },
  {
    icon: Coffee,
    title: "Cafés & work spots",
    text: "Study, work, relax",
  },
  {
    icon: Landmark,
    title: "Museums",
    text: "History, art, heritage",
  },
  {
    icon: Camera,
    title: "Attractions",
    text: "Must-see city spots",
  },
  {
    icon: Leaf,
    title: "Parks & nature",
    text: "Green escapes",
  },
  {
    icon: Music,
    title: "Nightlife",
    text: "Bars, clubs, live music",
  },
  {
    icon: ShoppingBag,
    title: "Shopping",
    text: "Malls, markets, boutiques",
  },
  {
    icon: Camera,
    title: "Photo spots",
    text: "Views and aesthetic places",
  },
];

const transportItems = [
  {
    icon: Plane,
    title: "Airport transfer",
    text: "From TIA to the city",
  },
  {
    icon: ParkingCircle,
    title: "Traffic & parking",
    text: "Busy areas & parking tips",
  },
  {
    icon: CarTaxiFront,
    title: "Taxi & ride apps",
    text: "Apps, tips & prices",
  },
  {
    icon: Footprints,
    title: "Walking in Tirana",
    text: "Best walking areas",
  },
  {
    icon: BusFront,
    title: "Public transport",
    text: "Buses, routes & tickets",
  },
  {
    icon: Bike,
    title: "Bike & scooter",
    text: "Rentals & tips",
  },
];

const cityGuide = [
  {
    icon: Sun,
    title: "Weather this week",
    text: "7-day forecast & rainy-day ideas",
    value: "22°C",
  },
  {
    icon: Coins,
    title: "Currency & exchange",
    text: "EUR / ALL rates and safe tips",
    value: "99.00 / 101.50",
  },
  {
    icon: Phone,
    title: "Emergency numbers",
    text: "Police, ambulance, fire & tourist help",
  },
  {
    icon: Languages,
    title: "Useful Albanian phrases",
    text: "Taxi, café, shopping and basics",
  },
  {
    icon: ShieldCheck,
    title: "Safety tips",
    text: "Practical advice for visitors",
  },
];

const dayTrips = [
  {
    image:
      "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=500&q=80",
    title: "Dajti",
    text: "Cable car & views",
  },
  {
    image:
      "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=500&q=80",
    title: "Bovilla Lake",
    text: "Hiking & nature",
  },
  {
    image:
      "https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=500&q=80",
    title: "Kruja",
    text: "Castle & bazaar",
  },
  {
    image:
      "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=500&q=80",
    title: "Berat",
    text: "UNESCO city",
  },
];

const deals = [
  {
    tag: "-20%",
    image:
      "https://images.unsplash.com/photo-1551183053-bf91a1d81141?auto=format&fit=crop&w=700&q=80",
    title: "20% off brunch",
    text: "Selected cafés · Until 14:00 today",
    category: "Food & Drinks",
  },
  {
    tag: "Student",
    image:
      "https://images.unsplash.com/photo-1564399579883-451a5d44ec08?auto=format&fit=crop&w=700&q=80",
    title: "Student museum ticket",
    text: "Bunk’Art 2, National Gallery",
    category: "Students",
  },
  {
    tag: "2-for-1",
    image:
      "https://images.unsplash.com/photo-1544145945-f90425340c7e?auto=format&fit=crop&w=700&q=80",
    title: "2-for-1 cocktails",
    text: "After 18:00 · Selected bars",
    category: "Nightlife",
  },
  {
    tag: "-15%",
    image:
      "https://images.unsplash.com/photo-1481437156560-3205f6a55735?auto=format&fit=crop&w=700&q=80",
    title: "15% off weekend",
    text: "Tirana East Gate Mall",
    category: "Shopping",
  },
];

function Explore() {
  return (
    <main className="explore-page">
      <section className="explore-top">
        <div className="explore-copy">
          <span className="explore-eyebrow">Explore Tirana</span>

          <h1>Find your next stop.</h1>

          <p>
            Search places, events, transport tips, day trips, deals and useful
            city info in one place.
          </p>
        </div>

        <a href="#picked-for-you" className="explore-pick-card">
          <img
            src="https://images.unsplash.com/photo-1533900298318-6b8da08a523e?auto=format&fit=crop&w=700&q=80"
            alt="Pazari i Ri"
          />

          <div>
            <span>
              <Star size={17} strokeWidth={2.4} />
              Today’s local pick
            </span>

            <h3>Pazari i Ri</h3>
            <p>Food, culture and an easy first stop.</p>
          </div>

          <ArrowRight size={18} strokeWidth={2.4} />
        </a>
      </section>

      <section className="explore-search-section">
        <div className="explore-search">
          <Search size={20} strokeWidth={2.3} />

          <input
            type="text"
            placeholder="Search cafés, attractions, events, airport transfer..."
          />
        </div>

        <button type="button" className="filter-btn" aria-label="Filters">
          <SlidersHorizontal size={20} strokeWidth={2.4} />
        </button>
      </section>

      <section className="explore-shortcuts">
        {shortcutCards.map((card) => {
          const Icon = card.icon;

          return (
            <a href={card.href} key={card.title}>
              <span>
                <Icon size={22} strokeWidth={2.3} />
              </span>

              <div>
                <h3>{card.title}</h3>
                <p>{card.text}</p>
              </div>
            </a>
          );
        })}
      </section>

      <section className="explore-panel picked-panel" id="picked-for-you">
        <div className="explore-section-head">
          <div>
            <h2>Picked for you</h2>
            <p>Based on your interests, budget and saved places.</p>
          </div>

          <a href="/foryou">
            Edit preferences <ArrowRight size={15} strokeWidth={2.5} />
          </a>
        </div>

        <div className="picked-grid">
          {pickedForYou.map((item) => (
            <article className="picked-card" key={item.title}>
              <div className="picked-image">
                <img src={item.image} alt={item.title} />
                <span>{item.tag}</span>
                <button type="button" aria-label="Save place">
                  <Bookmark size={18} strokeWidth={2.3} />
                </button>
              </div>

              <div className="picked-content">
                <h3>{item.title}</h3>
                <p>{item.meta}</p>
                <small>{item.text}</small>
                <b>{item.price}</b>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="explore-two-column">
        <section className="explore-panel" id="food-cafes">
          <div className="explore-section-head">
            <div>
              <h2>Food & cafés trending now</h2>
              <p>Popular places and spots people love right now.</p>
            </div>

            <a href="/explore">
              See all places <ArrowRight size={15} strokeWidth={2.5} />
            </a>
          </div>

          <div className="trending-grid">
            {trendingPlaces.map((place) => (
              <article className="place-card" key={place.title}>
                <div className="place-image">
                  <img src={place.image} alt={place.title} />
                  <button type="button" aria-label="Favorite">
                    <Heart size={20} strokeWidth={2.3} />
                  </button>
                </div>

                <div className="place-content">
                  <h3>{place.title}</h3>
                  <p>{place.meta}</p>
                  <small>{place.text}</small>
                  <b>{place.price}</b>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="explore-panel events-panel" id="events">
          <div className="explore-section-head">
            <div>
              <h2>Events this week</h2>
              <p>Don’t miss what’s happening in Tirana.</p>
            </div>

            <a href="/explore">
              See full calendar <ArrowRight size={15} strokeWidth={2.5} />
            </a>
          </div>

          <div className="event-list">
            {events.map((event) => (
              <article className="event-card" key={event.title}>
                <div className="event-date">
                  <span>{event.month}</span>
                  <strong>{event.day}</strong>
                  <small>{event.weekday}</small>
                </div>

                <div className="event-info">
                  <h3>{event.title}</h3>
                  <p>{event.time}</p>
                  <p>{event.location}</p>

                  <div>
                    <small>{event.type}</small>
                    <b>{event.price}</b>
                  </div>
                </div>

                <img src={event.image} alt={event.title} />

                <div className="event-actions">
                  <button type="button">
                    <Bookmark size={15} strokeWidth={2.4} />
                    Save
                  </button>

                  <button type="button">
                    <Navigation size={15} strokeWidth={2.4} />
                    Map
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      </section>

      <section className="explore-panel places-to-go" id="attractions-culture">
        <div className="explore-section-head">
          <div>
            <h2>Places to go</h2>
            <p>Food, cafés, attractions, culture, parks, nightlife and more.</p>
          </div>

          <a href="/explore">
            See all places <ArrowRight size={15} strokeWidth={2.5} />
          </a>
        </div>

        <div className="category-grid">
          {placeCategories.map((item) => {
            const Icon = item.icon;

            return (
              <article className="category-card" key={item.title}>
                <span>
                  <Icon size={22} strokeWidth={2.3} />
                </span>

                <div>
                  <h3>{item.title}</h3>
                  <p>{item.text}</p>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="explore-three-column">
        <section className="explore-panel" id="transport">
          <div className="explore-section-head">
            <div>
              <h2>Move around Tirana</h2>
              <p>Everything you need to get around.</p>
            </div>
          </div>

          <div className="mini-list-grid">
            {transportItems.map((item) => {
              const Icon = item.icon;

              return (
                <article className="mini-info-card" key={item.title}>
                  <span>
                    <Icon size={20} strokeWidth={2.3} />
                  </span>

                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.text}</p>
                  </div>
                </article>
              );
            })}
          </div>

          <a href="/explore" className="panel-link">
            See all transport info <ArrowRight size={15} strokeWidth={2.5} />
          </a>
        </section>

        <section className="explore-panel" id="city-guide">
          <div className="explore-section-head">
            <div>
              <h2>City guide</h2>
              <p>Useful information for a smooth day.</p>
            </div>
          </div>

          <div className="guide-list">
            {cityGuide.map((item) => {
              const Icon = item.icon;

              return (
                <article className="guide-row" key={item.title}>
                  <span>
                    <Icon size={19} strokeWidth={2.3} />
                  </span>

                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.text}</p>
                  </div>

                  {item.value && <b>{item.value}</b>}
                </article>
              );
            })}
          </div>

          <a href="/explore" className="panel-link">
            See all city guide <ArrowRight size={15} strokeWidth={2.5} />
          </a>
        </section>

        <section className="explore-panel" id="day-trips">
          <div className="explore-section-head">
            <div>
              <h2>Day trips from Tirana</h2>
              <p>Escapes, tours and group adventures.</p>
            </div>
          </div>

          <div className="trip-grid">
            {dayTrips.map((trip) => (
              <article className="trip-card" key={trip.title}>
                <img src={trip.image} alt={trip.title} />
                <h3>{trip.title}</h3>
                <p>{trip.text}</p>
              </article>
            ))}
          </div>

          <a href="/explore" className="panel-link">
            See all trips & tours <ArrowRight size={15} strokeWidth={2.5} />
          </a>
        </section>
      </section>

      <section className="explore-panel deals-panel" id="deals">
        <div className="explore-section-head">
          <div>
            <h2>Deals & discounts</h2>
            <p>Food deals, student offers, museums, tickets and shopping.</p>
          </div>

          <a href="/explore">
            See all deals <ArrowRight size={15} strokeWidth={2.5} />
          </a>
        </div>

        <div className="deal-tabs">
          <button className="active">All</button>
          <button>Food & Cafés</button>
          <button>Students</button>
          <button>Events</button>
          <button>Museums</button>
          <button>Shopping</button>
          <button>Rainy Day</button>
        </div>

        <div className="deals-grid">
          {deals.map((deal) => (
            <article className="deal-card" key={deal.title}>
              <div className="deal-image">
                <img src={deal.image} alt={deal.title} />
                <span>{deal.tag}</span>
              </div>

              <div>
                <h3>{deal.title}</h3>
                <p>{deal.text}</p>
                <small>{deal.category}</small>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

export default Explore;