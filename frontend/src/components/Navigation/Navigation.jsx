import { NavLink, Link } from "react-router-dom";
import "./navigation.css";

function Navigation({ isAuthenticated, onLogout, displayName }) {
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

        {isAuthenticated ? (
          <div className="nav-auth">
            <span className="nav-username">{displayName}</span>
            <button className="nav-logout-btn" onClick={onLogout}>
              Logout
            </button>
          </div>
        ) : (
          <Link to="/" className="nav-action">
            <span className="nav-action-icon">▣</span>
            Plan my day
          </Link>
        )}
      </div>
    </header>
  );
}

export default Navigation;
