import { useState, useEffect } from "react";
import "./App.css";
import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./components/Home/Home";
import Navigation from "./components/Navigation/Navigation";
import Footer from "./components/Footer/Footer";
import Ask from "./components/Ask/Ask";
import ForYou from "./components/ForYou/ForYou";
import Explore from "./components/Explore/Explore";
import Login from "./components/Authentication/Login";
import { checkSession, logout as apiLogout } from "./lib/api";

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [displayName, setDisplayName] = useState("");

  useEffect(() => {
    checkSession().then((valid) => {
      setIsAuthenticated(valid);
    });
  }, []);

  const handleLogin = (name) => {
    setDisplayName(name);
    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    await apiLogout();
    setIsAuthenticated(false);
    setDisplayName("");
  };

  if (isAuthenticated === null) {
    return <div className="app-loading">Loading...</div>;
  }

  if (!isAuthenticated) {
    return (
      <>
        <Navigation isAuthenticated={false} onLogout={handleLogout} displayName="" />
        <Login onClose={() => {}} onLogin={handleLogin} />
        <Footer />
      </>
    );
  }

  return (
    <>
      <Navigation
        isAuthenticated={true}
        onLogout={handleLogout}
        displayName={displayName}
      />

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/foryou" element={<ForYou />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Footer />
    </>
  );
}

export default App;