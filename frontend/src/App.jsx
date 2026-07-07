import { useState, useEffect } from "react";
import "./App.css";
import "./components/Global/pastel-bg.css";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Home from "./components/Home/Home";
import Navigation from "./components/Navigation/Navigation";
import Footer from "./components/Footer/Footer";
import Ask from "./components/Ask/Ask";
import ForYou from "./components/ForYou/ForYou";
import Explore from "./components/Explore/Explore";
import Global from "./components/Global/Global";
import Login from "./components/Authentication/Login";
import Register from "./components/Authentication/Register";
import { getUserProfile, logout as apiLogout } from "./lib/api";

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [displayName, setDisplayName] = useState("");
  // Auth modal: null (closed) | "login" | "register". Browsing is PUBLIC —
  // these only open when the user chooses to sign in, never as a wall.
  const [authModal, setAuthModal] = useState(null);
  const location = useLocation();

  // Tag <body> with the current page so pastel-bg.css can pick the
  // page-specific gradient blend (home / explore / ask / global / foryou).
  useEffect(() => {
    const page = location.pathname === "/" ? "home" : location.pathname.slice(1).split("/")[0];
    document.body.dataset.page = page;
  }, [location.pathname]);

  useEffect(() => {
    getUserProfile().then((profile) => {
      setIsAuthenticated(!!profile);
      if (profile) setDisplayName(profile.display_name || "");
    });
  }, []);

  const handleLogin = (name) => {
    setDisplayName(name);
    setIsAuthenticated(true);
    setAuthModal(null);
  };

  const handleRegister = (name) => {
    setDisplayName(name);
    setIsAuthenticated(true);
    // Don't close — their Register advances to the preferences step (step 2)
    // after account creation. Closing happens when the user finishes/skips.
  };

  const handleLogout = async () => {
    await apiLogout();
    setIsAuthenticated(false);
    setDisplayName("");
  };

  return (
    <>
      <Navigation
        isAuthenticated={isAuthenticated}
        displayName={displayName}
        onLogout={handleLogout}
        onOpenAuth={() => setAuthModal("login")}
      />

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/global" element={<Global />} />
        <Route path="/foryou" element={<ForYou isAuthenticated={isAuthenticated} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Footer />

      {authModal === "login" && (
        <Login
          onClose={() => setAuthModal(null)}
          onLogin={handleLogin}
          onSwitchToRegister={() => setAuthModal("register")}
        />
      )}

      {authModal === "register" && (
        <Register
          onClose={() => setAuthModal(null)}
          onRegistered={handleRegister}
          onSaved={() => setAuthModal(null)}
          onSwitch={() => setAuthModal("login")}
        />
      )}
    </>
  );
}

export default App;