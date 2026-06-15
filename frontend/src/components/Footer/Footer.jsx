import { Link } from "react-router-dom";
import "./footer.css";

function Footer() {
  const footerLinks = [
    { label: "Today", path: "/" },
    { label: "Explore", path: "/explore" },
    { label: "Ask", path: "/ask" },
  ];

  return (
    <footer className="footer">
      <div className="footer-container">
        <div className="footer-main">
          <div className="footer-brand">
            <Link to="/" className="footer-logo" aria-label="TiranaTips home">
              <span className="footer-logo-icon"></span>
              <span className="footer-logo-text">
                Tirana<span>Tips</span>
              </span>
            </Link>

            <p className="footer-description">
              A smart city guide for discovering Tirana, planning your day,
              and finding local tips that match your mood.
            </p>
          </div>

          <nav className="footer-links" aria-label="Footer navigation">
            <h4>City</h4>

            <div className="footer-link-list">
              {footerLinks.map((link) => (
                <Link key={link.label} to={link.path}>
                  {link.label}
                </Link>
              ))}
            </div>
          </nav>

          <div className="footer-note">
            <h4>Built for</h4>
            <p>
              Locals, visitors, students, remote workers, and curious people
              exploring Tirana.
            </p>
          </div>
        </div>

        <div className="footer-bottom">
          <p>© 2026 TiranaTips. Built for better city days.</p>
          <p>Discover Tirana your way.</p>
        </div>
      </div>
    </footer>
  );
}

export default Footer;