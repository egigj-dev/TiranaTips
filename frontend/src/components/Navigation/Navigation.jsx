import { NavLink, Link } from "react-router-dom";
import "./navigation.css";
import { getSessionToken } from "../../lib/api";

function Navigation({ isAuthenticated, onLogout, displayName, onOpenAuth }) {
  // Token is the source of truth. App's isAuthenticated can lag (login may
  // happen on another page), so fall back to the token to stay accurate.
  const loggedIn = isAuthenticated || !!getSessionToken();

  const navLinks = [
    { label: "Today", path: "/" },
    { label: "Explore", path: "/explore" },
    { label: "Ask", path: "/ask" },
    { label: "Global", path: "/global" },
    { label: "For You", path: "/foryou" },
  ];

  return (
    <header className="navigation">
      <div className="nav-container">
        <Link to="/" className="nav-logo" aria-label="TiranaTips home">
          <span className="nav-logo-icon"></span>
          <span className="nav-logo-text">
            Tirana<span>Tips</span>
          </span>
        </Link>

        <nav className="nav-menu" aria-label="Main navigation">
          {navLinks.map((link) => (
            <NavLink
              key={link.path}
              to={link.path}
              className={({ isActive }) =>
                isActive ? "nav-link nav-link-active" : "nav-link"
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        {loggedIn ? (
          <div className="nav-auth">
            {displayName && <span className="nav-username">{displayName}</span>}
            <button className="nav-logout-btn" onClick={onLogout}>
              Logout
            </button>
          </div>
        ) : (
          <div className="nav-auth">
            <button className="nav-login-btn" onClick={onOpenAuth}>
              Log in
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

export default Navigation;