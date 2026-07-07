import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./ask.css";

import "leaflet/dist/leaflet.css";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";

import {
  streamChat,
  getHistory,
  sendFeedback,
  getSessions,
  newSession,
  setSessionId,
  getSessionId,
  deleteSession,
  downloadSession,
  getSummaries,
  getUserId,
  getSessionToken,
  setStoredLanguage,
} from "../../lib/api";
import { getUserProfile, getUserLanguage } from "../../lib/auth";
import MapPanel from "../../components/MapPanel/MapPanel";

const mapMarkerIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const WELCOME_MESSAGE = {
  id: "welcome",
  type: "assistant",
  text: "Hi, I’m TiranaTips. Ask me like you would ask a local friend.",
  time: "Now",
  cardType: null,
  recommendations: null,
};

function Ask() {
  const [question, setQuestion] = useState("");
  const [selectedPlace, setSelectedPlace] = useState(null);
  const [selectedMapPlace, setSelectedMapPlace] = useState(null);
  const [savedPlaceIds, setSavedPlaceIds] = useState([]);
  const [toastMessage, setToastMessage] = useState("");

  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(getSessionId());
  const [isTyping, setIsTyping] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState({}); // {messageId: 1|-1}
  const [contextSession, setContextSession] = useState(null); // {session_id, display_name}
  const [showContextPicker, setShowContextPicker] = useState(false);
  // User's stored language from their profile. Read from localStorage first
  // (persisted on login/register), then re-sync from the profile fetch below
  // in case the user changed language on another device.
  const [userLanguage, setUserLanguage] = useState(getUserLanguage());
  // Ref to buffer English tokens silently when translation is pending, so the
  // user never sees the English answer flash before the translated version.
  const tokenBufferRef = useRef("");
  // Synchronous guard against rapid double-sends. React state (isStreaming)
  // updates asynchronously, so two clicks in the same tick both see it false;
  // a ref flips immediately and blocks the second one.
  const isStreamingRef = useRef(false);
  // Map data for the currently open map modal.
  const [activeMapData, setActiveMapData] = useState(null);
  // Whether the map drawer is visible. Closing the drawer doesn't lose the
  // last result — the floating toggle can reopen it without re-asking.
  const [isMapOpen, setIsMapOpen] = useState(false);


  const mostAsked = [
    "Good coffee near Blloku?",
    "Best restaurants near Blloku?",
    "Best time to go to Dajti?",
    "Where can I exchange money?",
    "What can I do tonight?",
  ];

  // Languages non-logged-in users can pick for their chat answers.
  // Logged-in users control language from their For You page.
  const LANGUAGE_OPTIONS = [
    { code: "auto", label: "Auto (detect)" },
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

  const handleLanguageSelect = (e) => {
    const lang = e.target.value;
    setUserLanguage(lang);
    setStoredLanguage(lang);
  };

  // -------------------------------------------------------------------------
  // Restore the active session's history. Re-runs when the user switches
  // sessions from the sidebar (activeSession change), not just on mount.
  // -------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    getHistory()
      .then(({ messages: past }) => {
        if (cancelled) return;
        if (!past || past.length === 0) {
          setMessages([WELCOME_MESSAGE]);
          return;
        }
        const restored = past.map((m, i) => ({
          id: `h-${i}`,
          type: m.role === "user" ? "user" : "assistant",
          text: m.content,
          // The user question preceding each assistant turn — needed for the
          // feedback endpoint, which rates (question, answer) pairs.
          question: m.role === "assistant" ? past[i - 1]?.content : undefined,
          time: "Earlier",
          cardType: null,
          recommendations: null,
        }));
        setMessages([WELCOME_MESSAGE, ...restored]);
      })
      .catch(() => {
        // History is a nicety — a fresh chat is a fine fallback.
        if (!cancelled) setMessages([WELCOME_MESSAGE]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeSession]);

  // Past chat threads for the sidebar. refreshSessions() is called after any
  // mutation (new message persisted, rename, delete) to keep the list current.
  const refreshSessions = () =>
    getSessions(getUserId())
      .then(({ sessions: list }) => setSessions(list || []))
      .catch(() => {});

  useEffect(() => {
    refreshSessions();
  }, []);

  // Fetch the authenticated user's profile language on mount so every chat
  // request uses the user's chosen language instead of "auto".
  useEffect(() => {
    getUserProfile().then((profile) => {
      if (profile?.language) {
        setUserLanguage(profile.language);
      }
    }).catch(() => {
      // Not logged in — keep whatever localStorage has (likely "auto").
    });
  }, []);

  const openSession = (sessionId) => {
    if (sessionId === activeSession) return;
    setSessionId(sessionId);
    setActiveSession(sessionId); // triggers the history effect above
  };

  const startNewChat = () => {
    const id = newSession();
    setActiveSession(id);
    setMessages([WELCOME_MESSAGE]);
    setContextSession(null);
  };

  const startNewChatWithContext = () => {
    // First create the new session, then open the context picker
    const id = newSession();
    setActiveSession(id);
    setMessages([WELCOME_MESSAGE]);
    setShowContextPicker(true);
  };

  const loadContext = (ctx) => {
    setContextSession(ctx);
    setShowContextPicker(false);
  };

  const clearContext = () => setContextSession(null);

  const removeSession = async (sessionId, event) => {
    event.stopPropagation(); // don't also trigger openSession on the row
    await deleteSession(sessionId).catch(() => {});
    if (sessionId === activeSession) startNewChat();
    refreshSessions();
  };

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

  // -------------------------------------------------------------------------
  // Send a question → stream the answer token by token.
  //
  // Flow per backend contract:
  //   1. `sources` event arrives first → stash on the pending message
  //   2. optional `generating` event → show "Searching..." placeholder
  //   3. `token` events append text (buffered silently when translation is
  //      pending so the user never sees English flash before translation)
  //   4. optional `translation` event REPLACES the full text with the
  //      user-language version
  //   5. `final` event REPLACES the text with the link-injected version, so
  //      place mentions become highlighted Google Maps links live
  //   6. `done` ends the stream; `low_confidence` short-circuits with a
  //      fallback message instead of tokens.
  // -------------------------------------------------------------------------
  const sendQuestion = async (textToSend) => {
    const trimmed = textToSend.trim();
    if (!trimmed || isStreamingRef.current) return;
    isStreamingRef.current = true;

    const userMessage = {
      id: Date.now(),
      type: "user",
      text: trimmed,
      time: "Now",
      cardType: null,
      recommendations: null,
    };

    const assistantId = Date.now() + 1;

    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setIsTyping(true);
    setIsStreaming(true);

    // Helper: patch the in-flight assistant message immutably.
    const patchAssistant = (patch) =>
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, ...patch(m) } : m))
      );

    let bubbleCreated = false;
    const ensureBubble = () => {
      if (bubbleCreated) return;
      bubbleCreated = true;
      setIsTyping(false);
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          type: "assistant",
          text: "",
          question: trimmed,
          sources: [],
          time: "Just now",
          cardType: null,
          recommendations: null,
          mapData: null,
        },
      ]);
    };

    // Whether the backend will produce a translation event. When true, we
    // buffer English tokens silently in the ref and only show the final
    // translated text — no flashing "English then swap" UX.
    const needsTranslation =
      userLanguage && userLanguage !== "auto" && userLanguage !== "en";
    // Reset the silent buffer for each question.
    tokenBufferRef.current = "";

    try {
      await streamChat(
        { question: trimmed, language: userLanguage, context_session_id: contextSession?.session_id },
        {
          onSources: (sources) => {
            ensureBubble();
            patchAssistant(() => ({ sources }));
          },
          onMap: (mapData) => {
            console.log("[map]", mapData);   // ← verify line (remove after)
            ensureBubble();
            patchAssistant(() => ({ mapData }));
            setActiveMapData(mapData);
            setIsMapOpen(true);
          },
          onGenerating: () => {
            ensureBubble();
            // Show a searching indicator while the backend generates the
            // English answer (which we buffer silently until translation).
            patchAssistant(() => ({ text: "Searching for the best answer…" }));
          },
          onToken: (token) => {
            ensureBubble();
            if (needsTranslation) {
              // Buffer silently — the user sees the "Searching…" placeholder
              // until the translation event replaces it.
              tokenBufferRef.current += token;
            } else {
              // English-only: stream tokens directly as before.
              patchAssistant((m) => ({ text: m.text + token }));
            }
          },
          onTranslation: (text) => {
            // Replace the placeholder (or any partial text) with the final
            // translated answer in the user's language.
            patchAssistant(() => ({ text }));
          },
          onLowConfidence: (message) => {
            ensureBubble();
            patchAssistant(() => ({ text: message, sources: [] }));
          },
          onFinal: (text) => {
            // Final answer with Google Maps links injected — replaces the
            // streamed (raw) text so place names render as highlighted links.
            patchAssistant(() => ({ text }));
          },
        }
      );
    } catch (err) {
      console.error(err);
      ensureBubble();
      // err.status is set by api.js for HTTP failures; map the two
      // user-fixable cases to actionable messages instead of "outage".
      const friendly =
        err.status === 429
          ? "You’re sending messages a bit too fast — wait a moment and try again."
          : err.status === 422
            ? "That question is too long — please shorten it (max 1000 characters)."
            : err.status === 403
              ? "This conversation belongs to an account — start a new chat to ask anonymously."
              : "Sorry — I couldn’t reach the server. Please try again in a moment.";
      patchAssistant((m) => ({ text: m.text || friendly }));
    } finally {
      setIsTyping(false);
      setIsStreaming(false);
      isStreamingRef.current = false;
      // A first message in a new thread creates the session (and its
      // auto-generated name) server-side — refresh so it shows in the sidebar.
      refreshSessions();
    }
  };

  // Thumbs up/down on an assistant answer. On -1 the backend also evicts
  // every cached variant of the question so the bad answer isn't replayed.
  const handleFeedback = async (message, rating) => {
    if (!message.question || feedbackGiven[message.id]) return;
    setFeedbackGiven((prev) => ({ ...prev, [message.id]: rating }));
    try {
      await sendFeedback(message.question, rating);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    sendQuestion(question);
  };

  return (
    <main className="ask-page">
      {/* <section className="ask-intro">
        <div className="ask-decor ask-decor-left">
          <span className="tt-logo-icon hero-corner-logo" aria-hidden="true"></span>          <span className="decor-leaf decor-leaf-one"></span>
          <span className="decor-leaf decor-leaf-two"></span>
        </div>

        <div className="ask-decor ask-decor-right">
          <span className="decor-tower"></span>
          <span className="decor-statue"></span>
          <span className="decor-building"></span>
        </div>
      </section> */}

      <section className="assistant-shell">
        {isMapOpen ? (
          <aside className="assistant-map-panel">
            <div className="map-panel-header">
              <span>🗺️ Map</span>
              <button
                type="button"
                className="map-panel-back"
                onClick={() => setIsMapOpen(false)}
                aria-label="Close map and return to sidebar"
              >
                ← Back
              </button>
            </div>
            <MapPanel activeMapData={activeMapData} />
            {activeMapData?.directions_url && (
              <a
                className="map-open-external"
                href={activeMapData.directions_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open in Google Maps
              </a>
            )}
          </aside>
        ) : (
          <aside className="assistant-side">
            <div className="side-logo">
              <span className="tt-logo-icon" aria-hidden="true"></span>
              <div>
                <h2>Ask Tirana</h2>
                <p>Your AI local assistant</p>
              </div>
            </div>

            <button
              type="button"
              className="new-chat-btn"
              onClick={startNewChat}
            >
              + New chat
            </button>

            {sessions.length > 0 && (
              <div className="session-list">
                <h3>Your chats</h3>
                {sessions.map((s) => (
                  <div
                    key={s.session_id}
                    className={
                      "session-row" +
                      (s.session_id === activeSession ? " session-active" : "")
                    }
                    onClick={() => openSession(s.session_id)}
                  >
                    <span className="session-name">{s.display_name}</span>
                    <div className="session-actions">
                      <button
                        type="button"
                        className="session-download"
                        aria-label="Download chat"
                        onClick={(e) => {
                          e.stopPropagation();
                          downloadSession(s.session_id, s.display_name);
                        }}
                        title="Download chat"
                      >
                        ⬇
                      </button>
                      <button
                        type="button"
                        className="session-delete"
                        aria-label="Delete chat"
                        onClick={(e) => removeSession(s.session_id, e)}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="sidebar-actions">
              <button
                type="button"
                className="context-btn"
                onClick={startNewChatWithContext}
                title="Start a new chat with context from a past conversation"
              >
                <span>📋</span>
                New with context
              </button>
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

            <div className="ask-language-picker">
              <h3>Language</h3>
              <select
                value={userLanguage || "auto"}
                onChange={handleLanguageSelect}
                aria-label="Chat language"
              >
                {LANGUAGE_OPTIONS.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
          </aside>
        )}

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
                    <span className="tt-logo-icon sm" aria-hidden="true"></span>
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

                  {message.type === "user" ? (
                    <p>{message.text}</p>
                  ) : (
                    <div className="markdown-content">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          // Render links in a new tab. Place mentions (links to
                          // Google Maps) get a highlight class so they read as
                          // tappable chips.
                          a: ({ href, children }) => {
                            const isPlace =
                              typeof href === "string" &&
                              /google\.com\/maps|maps\.google\.|goo\.gl\/maps|maps\.app\.goo\.gl/.test(href);
                            return (
                              <a
                                href={href}
                                target="_blank"
                                rel="noreferrer"
                                className={isPlace ? "place-link" : undefined}
                              >
                                {children}
                              </a>
                            );
                          },
                        }}
                      >
                        {message.text}
                      </ReactMarkdown>
                    </div>
                  )}

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

                  {/* Source pills — web/event/doc links only. Place sources are
                      NOT shown here: they already appear inline in the answer
                      as highlighted Maps links, so a pill row would duplicate
                      them. */}
                  {message.sources?.some(
                    (s) => s.type !== "local" && s.type !== "place"
                  ) && (
                    <div className="message-sources">
                      {message.sources
                        .filter((s) => s.type !== "local" && s.type !== "place")
                        .map((source, i) =>
                          source.url ? (
                            <a key={i} href={source.url} target="_blank" rel="noreferrer">
                              {source.type === "event" ? "📅" : "🌐"}{" "}
                              {source.title}
                            </a>
                          ) : (
                            <span key={i}>📄 {source.title || source}</span>
                          )
                        )}
                    </div>
                  )}

                  {message.type === "assistant" && message.question && (
                    <div className="message-feedback">
                      <button
                        type="button"
                        className={
                          feedbackGiven[message.id] === 1 ? "is-rated" : ""
                        }
                        disabled={!!feedbackGiven[message.id]}
                        onClick={() => handleFeedback(message, 1)}
                        aria-label="Good answer"
                      >
                        👍
                      </button>
                      <button
                        type="button"
                        className={
                          feedbackGiven[message.id] === -1 ? "is-rated" : ""
                        }
                        disabled={!!feedbackGiven[message.id]}
                        onClick={() => handleFeedback(message, -1)}
                        aria-label="Bad answer"
                      >
                        👎
                      </button>
                    </div>
                  )}

                  <small>{message.time}</small>
                </div>
              </div>
            ))}

            {isTyping && (
              <div className="message-row">
                <div className="assistant-avatar">
                  <span className="tt-logo-icon sm" aria-hidden="true"></span>
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
              maxLength={1000}
              disabled={isStreaming}
            />

            <button type="submit" disabled={isStreaming}>
              Send
            </button>
          </form>
          {activeMapData && !isMapOpen && (
            <button
              type="button"
              className="map-toggle-btn"
              onClick={() => setIsMapOpen(true)}
              aria-label="Show map"
              title="Show map"
            >
              🗺️ Map
            </button>
          )}
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

      {contextSession && (
        <div className="context-banner">
          <span>📋 Context loaded: <strong>{contextSession.display_name}</strong></span>
          <button type="button" onClick={clearContext} title="Remove context">
            ×
          </button>
        </div>
      )}

      {showContextPicker && (
        <ContextPickerModal
          currentSessionId={activeSession}
          onSelect={loadContext}
          onClose={() => setShowContextPicker(false)}
        />
      )}
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
  const googleMapsUrl =
    place.maps_url ||
    `https://www.google.com/maps/search/?api=1&query=${place.lat},${place.lng}`;

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

function ContextPickerModal({ currentSessionId, onSelect, onClose }) {
  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  // /summaries is account-scoped now; without a token it 401s. Distinguish
  // "logged out" from "logged in but no summaries yet".
  const [needsLogin, setNeedsLogin] = useState(false);

  useEffect(() => {
    if (!getSessionToken()) {
      setNeedsLogin(true);
      setLoading(false);
      return;
    }
    getSummaries()
      .then((data) => {
        // Filter out the current session (no point importing your own context)
        const filtered = (data.summaries || []).filter(
          (s) => s.session_id !== currentSessionId
        );
        setSummaries(filtered);
      })
      .catch(() => setNeedsLogin(!getSessionToken()))
      .finally(() => setLoading(false));
  }, [currentSessionId]);

  const truncate = (text, max = 120) =>
    text.length > max ? text.slice(0, max) + "…" : text;

  return (
    <div className="context-picker-overlay" onClick={onClose}>
      <article
        className="context-picker-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="context-picker-header">
          <h2>📋 Load past conversation context</h2>
          <p>
            Choose a past chat to inject its summary into this new
            conversation. The AI will be aware of what you discussed before.
          </p>
          <button
            type="button"
            className="context-picker-close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        {needsLogin ? (
          <div className="context-picker-empty">
            <p>Log in to use saved context.</p>
            <p className="context-picker-hint">
              Past-conversation summaries are tied to your account. Create an
              account or log in, then chat — a summary is generated
              automatically after 10 messages.
            </p>
          </div>
        ) : loading ? (
          <div className="context-picker-loading">Loading summaries…</div>
        ) : summaries.length === 0 ? (
          <div className="context-picker-empty">
            <p>No saved summaries found.</p>
            <p className="context-picker-hint">
              Summaries are automatically generated after 10 messages in a
              chat. Keep chatting to create one.
            </p>
          </div>
        ) : (
          <div className="context-picker-table-wrap">
            <table className="context-picker-table">
              <thead>
                <tr>
                  <th>Chat</th>
                  <th>Summary</th>
                  <th>Messages</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {summaries.map((s) => (
                  <tr key={s.session_id}>
                    <td className="ctx-name">{s.display_name}</td>
                    <td className="ctx-summary">{truncate(s.summary)}</td>
                    <td className="ctx-count">{s.message_count}</td>
                    <td className="ctx-action">
                      <button
                        type="button"
                        className="ctx-use-btn"
                        onClick={() =>
                          onSelect({
                            session_id: s.session_id,
                            display_name: s.display_name,
                          })
                        }
                      >
                        Use
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </div>
  );
}

export default Ask;