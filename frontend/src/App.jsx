import { useState, useEffect } from "react";
import "./App.css";
import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./components/Home/Home";
import Navigation from "./components/Navigation/Navigation";
import Footer from "./components/Footer/Footer";
import Ask from "./components/Ask/Ask";
import ForYou from "./components/ForYou/ForYou";
import Explore from "./components/Explore/Explore";
import Global from "./components/Global/Global";
import Login from "./components/Authentication/Login";
import Register from "./components/Authentication/Register";
import { checkSession, logout as apiLogout } from "./lib/api";

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [displayName, setDisplayName] = useState("");
  // Auth modal: null (closed) | "login" | "register". Browsing is PUBLIC —
  // these only open when the user chooses to sign in, never as a wall.
  const [authModal, setAuthModal] = useState(null);

  useEffect(() => {
    checkSession().then((valid) => setIsAuthenticated(valid));
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