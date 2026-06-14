import { useState, useEffect } from "react";
import "./App.css";
import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./components/Home/Home";
import Navigation from "./components/Navigation/Navigation";
import Footer from "./components/Footer/Footer";
import Ask from "./components/Ask/Ask";
import ForYou from "./components/ForYou/ForYou";
import Login from "./components/Authentication/Login";
import { checkSession, logout as apiLogout } from "./lib/api";

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(null); // null = checking
  const [showLogin, setShowLogin] = useState(false);
  const [userDisplayName, setUserDisplayName] = useState("");

  // On mount, check if there's a valid session
  useEffect(() => {
    checkSession().then((valid) => {
      setIsAuthenticated(valid);
      if (!valid) {
        setShowLogin(true);
      }
    });
  }, []);

  const handleLogin = () => {
    setIsAuthenticated(true);
    setShowLogin(false);
  };

  const handleLogout = async () => {
    await apiLogout();
    setIsAuthenticated(false);
    setShowLogin(true);
    setUserDisplayName("");
  };

  // While checking session, show nothing (or a loading spinner)
  if (isAuthenticated === null) {
    return <div className="app-loading">Loading...</div>;
  }

  // If not authenticated, show login modal and block everything else
  if (!isAuthenticated) {
    return (
      <>
        <Navigation isAuthenticated={false} onLogout={handleLogout} displayName="" />
        <Login onClose={() => {}} onLogin={handleLogin} />
        <Footer />
      </>
    );
  }

  // Authenticated — show the full app
  return (
    <>
      <Navigation
        isAuthenticated={true}
        onLogout={handleLogout}
        displayName={userDisplayName}
      />

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/foryou" element={<ForYou />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Footer />
    </>
  );
}

export default App;
