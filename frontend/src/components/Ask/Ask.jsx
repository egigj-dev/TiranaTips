import { useState } from "react";
import "./ask.css";

import "leaflet/dist/leaflet.css";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";

const mapMarkerIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

function Ask() {
  const [question, setQuestion] = useState("");
  const [selectedPlace, setSelectedPlace] = useState(null);
  const [selectedMapPlace, setSelectedMapPlace] = useState(null);
  const [savedPlaceIds, setSavedPlaceIds] = useState([]);
  const [toastMessage, setToastMessage] = useState("");

  const [messages, setMessages] = useState([
    {
      id: 1,
      type: "assistant",
      text: "Hi, I’m TiranaTips. Ask me like you would ask a local friend.",
      time: "Now",
      cardType: null,
      recommendations: null,
    },
  ]);

  const [isTyping, setIsTyping] = useState(false);

  const mostAsked = [
    "Good coffee near Blloku?",
    "Best restaurants near Blloku?",
    "Best time to go to Dajti?",
    "Where can I exchange money?",
    "What can I do tonight?",
  ];

  const handleSavePlace = (place) => {
    setSavedPlaceIds((prev) => {
      const isAlreadySaved = prev.includes(place.id);

      if (isAlreadySaved) {
        setToastMessage(`${place.name} removed from your saved places`);

        setTimeout(() => {
          setToastMessage("");
        }, 2200);

        return prev.filter((id) => id !== place.id);
      }

      setToastMessage(`${place.name} saved to your places`);

      setTimeout(() => {
        setToastMessage("");
      }, 2200);

      return [...prev, place.id];
    });
  };
  const getDemoAnswer = (userQuestion) => {
    const text = userQuestion.toLowerCase();

    if (
      text.includes("restaurant") ||
      text.includes("food") ||
      text.includes("eat") ||
      text.includes("blloku") ||
      text.includes("dinner")
    ) {
      return {
        text: "Here are 3 good options near Blloku depending on your vibe: modern Albanian dining, casual brunch, or traditional food.",
        cardType: "recommendationList",
        recommendations: {
          title: "Top recommendations near Blloku",
          items: [
            {
              id: 1,
              name: "Mullixhiu",
              lat: 41.3186,
              lng: 19.8167,
              tag: "Top pick",
              type: "Modern Albanian dining",
              area: "Blloku / near Grand Park",
              rating: "4.8",
              price: "Mid-high",
              image:
                "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=700&q=80",
              bestFor: "Dinner & local cuisine",
              tip: "Reserve ahead, especially on weekends.",
              sentiment: "Mostly positive",
              reviewSummary:
                "People like the atmosphere, food quality, and modern Albanian style. Some mention that it can get crowded during dinner and prices are a bit high.",
              liked: ["Great atmosphere", "Good service", "Food quality"],
              watchOut: [
                "Can be crowded",
                "Prices are a bit high",
                "Reservation recommended",
              ],
            },
            {
              id: 2,
              name: "Salt Tirana",
              lat: 41.3211,
              lng: 19.8147,
              tag: "Café / brunch",
              type: "Modern café",
              area: "Blloku",
              rating: "4.7",
              price: "Mid-range",
              image:
                "https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=700&q=80",
              bestFor: "Coffee, brunch & casual lunch",
              tip: "Good daytime vibe.",
              sentiment: "Positive",
              reviewSummary:
                "People like the coffee, brunch options, and modern atmosphere. It can feel busy during peak hours.",
              liked: ["Good coffee", "Nice brunch", "Modern interior"],
              watchOut: ["Busy at peak hours", "Can be noisy"],
            },
            {
              id: 3,
              name: "Era Blloku",
              lat: 41.3214,
              lng: 19.8162,
              tag: "Traditional",
              type: "Albanian cuisine",
              area: "Blloku",
              rating: "4.6",
              price: "Mid-range",
              image:
                "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=700&q=80",
              bestFor: "Classic local food",
              tip: "Good for first-time visitors.",
              sentiment: "Mostly positive",
              reviewSummary:
                "People like the traditional Albanian dishes, friendly service, and central location. Some mention that it can be full during dinner.",
              liked: ["Traditional food", "Friendly service", "Good location"],
              watchOut: ["Can be full", "Reservation helps"],
            },
          ],
        },
      };
    }

    if (text.includes("rain")) {
      return {
        text: "If it rains, keep your plan indoor and simple: a warm café, a museum or gallery, then dinner somewhere cozy.",
        cardType: null,
        recommendations: null,
      };
    }

    if (text.includes("safe")) {
      return {
        text: "Central Tirana is generally comfortable to explore. At night, stay in well-lit areas, keep an eye on your belongings, and use taxis if you are far from the center.",
        cardType: null,
        recommendations: null,
      };
    }

    if (text.includes("calm")) {
      return {
        text: "For a calm afternoon, start with coffee near the city center, walk around Liqeni i Tiranës, then end with an early dinner somewhere quiet.",
        cardType: null,
        recommendations: null,
      };
    }

    return {
      text: "A simple Tirana plan: start with coffee, choose one area to explore, check what events are happening tonight, and finish with dinner somewhere local.",
      cardType: null,
      recommendations: null,
    };
  };

  const sendQuestion = (textToSend) => {
    if (!textToSend.trim()) return;

    const userMessage = {
      id: Date.now(),
      type: "user",
      text: textToSend,
      time: "Now",
      cardType: null,
      recommendations: null,
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setIsTyping(true);

    setTimeout(() => {
      const answer = getDemoAnswer(textToSend);

      const assistantMessage = {
        id: Date.now() + 1,
        type: "assistant",
        text: answer.text,
        time: "Just now",
        cardType: answer.cardType,
        recommendations: answer.recommendations,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setIsTyping(false);
    }, 650);
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    sendQuestion(question);
  };

  return (
    <main className="ask-page">
      <section className="ask-intro">
        <div className="ask-decor ask-decor-left">
          <span className="ask-logo-icon hero-corner-logo"></span>
          <span className="decor-leaf decor-leaf-one"></span>
          <span className="decor-leaf decor-leaf-two"></span>
        </div>

        <div className="ask-decor ask-decor-right">
          <span className="decor-tower"></span>
          <span className="decor-statue"></span>
          <span className="decor-building"></span>
        </div>

        <div className="ask-intro-content">
          <span className="ask-eyebrow">Ask TiranaTips</span>

          <h1>
            What do you need to know <br /> about Tirana today?
          </h1>

          <p>
            Get quick local answers for food, events, transport, safety, money,
            nightlife, and daily plans.
          </p>
        </div>
      </section>

      <section className="assistant-shell">
        <aside className="assistant-side">
          <div className="side-logo">
            <span className="ask-logo-icon"></span>

            <div>
              <h2>Ask Tirana</h2>
              <p>Your AI local assistant</p>
            </div>
          </div>

          <div className="most-asked">
            <h3>Most asked</h3>

            {mostAsked.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => sendQuestion(item)}
              >
                <span>{item}</span>
                <b>›</b>
              </button>
            ))}
          </div>
        </aside>

        <section className="assistant-chat">
          <div className="chat-messages">
            {messages.map((message) => (
              <div
                key={message.id}
                className={
                  message.type === "user"
                    ? "message-row message-row-user"
                    : "message-row"
                }
              >
                {message.type === "assistant" && (
                  <div className="assistant-avatar">
                    <span className="ask-logo-icon"></span>
                  </div>
                )}

                <div
                  className={
                    message.type === "user"
                      ? "message-bubble user-message"
                      : "message-bubble assistant-message"
                  }
                >
                  {message.type === "assistant" && <strong>TiranaTips</strong>}

                  <p>{message.text}</p>

                  {message.cardType === "recommendationList" &&
                    message.recommendations && (
                      <RecommendationListCard
                        data={message.recommendations}
                        onAskFollowUp={sendQuestion}
                        onOpenPlace={setSelectedPlace}
                        onOpenMap={setSelectedMapPlace}
                        onSavePlace={handleSavePlace}
                        savedPlaceIds={savedPlaceIds}
                      />
                    )}

                  <small>{message.time}</small>
                </div>
              </div>
            ))}

            {isTyping && (
              <div className="message-row">
                <div className="assistant-avatar">
                  <span className="ask-logo-icon"></span>
                </div>

                <div className="typing-bubble">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            )}
          </div>

          <form className="chat-form" onSubmit={handleSubmit}>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask me anything about Tirana..."
            />

            <button type="submit">Send</button>
          </form>
        </section>
      </section>

      {selectedPlace && (
        <PlaceDetailsModal
          place={selectedPlace}
          onClose={() => setSelectedPlace(null)}
          onAskFollowUp={sendQuestion}
        />
      )}

      {selectedMapPlace && (
        <PlaceMapModal
          place={selectedMapPlace}
          onClose={() => setSelectedMapPlace(null)}
        />
      )}

      {toastMessage && <div className="save-toast">{toastMessage}</div>}
    </main>
  );
}

function RecommendationListCard({
  data,
  onAskFollowUp,
  onOpenPlace,
  onOpenMap,
  onSavePlace,
  savedPlaceIds,
}) {
  return (
    <article className="recommendation-list-card">
      <div className="recommendation-list-header">
        <div>
          <span className="recommendation-icon">✧</span>
          <h3>{data.title}</h3>
        </div>
      </div>

      <div className="recommendation-items">
        {data.items.map((place) => {
          const isSaved = savedPlaceIds.includes(place.id);

          return (
            <article className="recommendation-item" key={place.id}>
              <div className="recommendation-image">
                <img src={place.image} alt={place.name} />
                <span>{place.tag}</span>
              </div>

              <div className="recommendation-content">
                <button
                  type="button"
                  className={`mini-save-btn ${isSaved ? "is-saved" : ""}`}
                  onClick={() => onSavePlace(place)}
                  aria-label={isSaved ? "Saved place" : "Save place"}
                >
                  {isSaved ? "♥" : "♡"}
                </button>

                <div className="recommendation-title-row">
                  <h4>{place.name}</h4>
                  <p>{place.type}</p>
                </div>

                <button
                  type="button"
                  className="recommendation-meta recommendation-meta-button"
                  onClick={() => onOpenPlace(place)}
                >
                  <span>★ {place.rating} rating</span>
                  <span>Price: {place.price}</span>
                  <span>{place.area}</span>
                </button>

                <div className="recommendation-info">
                  <p>
                    <b>Best for:</b> {place.bestFor}
                  </p>

                  <p>
                    <b>Tip:</b> {place.tip}
                  </p>
                </div>
              </div>

              <div className="recommendation-actions">
                <button type="button" onClick={() => onOpenMap(place)}>
                  Open map
                </button>

                <button
                  type="button"
                  className={isSaved ? "saved-action-btn" : ""}
                  onClick={() => onSavePlace(place)}
                >
                  {isSaved ? "Saved" : "Save"}
                </button>

                <button type="button" onClick={() => onOpenPlace(place)}>
                  Details
                </button>
              </div>
            </article>
          );
        })}
      </div>

      <div className="recommendation-footer-actions">
        <button type="button">Show more</button>

        <button
          type="button"
          onClick={() => onAskFollowUp("Find cheaper restaurants near Blloku")}
        >
          Make it cheaper
        </button>

        <button
          type="button"
          onClick={() => onAskFollowUp("Plan a dinner route near Blloku")}
        >
          Plan dinner route
        </button>
      </div>
    </article>
  );
}

function PlaceMapModal({ place, onClose }) {
  const googleMapsUrl = `https://www.google.com/maps/search/?api=1&query=${place.lat},${place.lng}`;

  return (
    <div className="place-modal-overlay">
      <article className="place-map-modal">
        <button type="button" className="place-modal-close" onClick={onClose}>
          ×
        </button>

        <div className="place-map-header">
          <span>Map preview</span>
          <h2>{place.name}</h2>
          <p>{place.area}</p>
        </div>

        <div className="single-place-map">
          <MapContainer
            center={[place.lat, place.lng]}
            zoom={16}
            scrollWheelZoom={true}
            dragging={true}
            doubleClickZoom={true}
            zoomControl={true}
            className="leaflet-single-place-map"
          >
            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            <Marker position={[place.lat, place.lng]} icon={mapMarkerIcon}>
              <Popup>
                <strong>{place.name}</strong>
                <br />
                {place.area}
              </Popup>
            </Marker>
          </MapContainer>
        </div>

        <div className="place-map-actions">
          <a href={googleMapsUrl} target="_blank" rel="noreferrer">
            Open in Google Maps
          </a>

          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </article>
    </div>
  );
}

function PlaceDetailsModal({ place, onClose, onAskFollowUp }) {
  return (
    <div className="place-modal-overlay">
      <article className="place-details-modal">
        <button type="button" className="place-modal-close" onClick={onClose}>
          ×
        </button>

        <div className="place-modal-image">
          <img src={place.image} alt={place.name} />

          <div>
            <span>{place.tag}</span>
            <h2>{place.name}</h2>
            <p>
              {place.type} · {place.area}
            </p>
          </div>
        </div>

        <div className="place-modal-content">
          <div className="place-modal-meta">
            <span>★ {place.rating} rating</span>
            <span>Price: {place.price}</span>
            <span>{place.sentiment}</span>
          </div>

          <div className="place-modal-info-row">
            <div className="place-modal-section">
              <h3>Best for</h3>
              <p>{place.bestFor}</p>
            </div>

            <div className="place-modal-section">
              <h3>Local tip</h3>
              <p>{place.tip}</p>
            </div>
          </div>

          <div className="ai-review-summary">
            <div>
              <span>AI Review Summary</span>
              <strong>{place.sentiment}</strong>
            </div>

            <p>{place.reviewSummary}</p>
          </div>

          <div className="review-insights-grid">
            <div>
              <h3>People like</h3>

              {place.liked.map((item) => (
                <p key={item}>✓ {item}</p>
              ))}
            </div>

            <div>
              <h3>Watch out</h3>

              {place.watchOut.map((item) => (
                <p key={item}>⚠ {item}</p>
              ))}
            </div>
          </div>

          <div className="place-modal-actions">
            <button type="button">Open map</button>
            <button type="button">Save place</button>
            <button
              type="button"
              onClick={() => {
                onClose();
                onAskFollowUp(`Find cheaper options like ${place.name}`);
              }}
            >
              Ask cheaper options
            </button>
          </div>
        </div>
      </article>
    </div>
  );
}

export default Ask;