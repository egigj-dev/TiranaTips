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

          <div className="footer-note footer-emergency">
            <h4>Emergency</h4>

            <div className="footer-emergency-list">
              <p>
                <strong>112</strong>
                <span>General Emergency</span>
              </p>

              <p>
                <strong>129</strong>
                <span>Police</span>
              </p>

              <p>
                <strong>127</strong>
                <span>Ambulance</span>
              </p>

              <p>
                <strong>128</strong>
                <span>Fire Brigade</span>
              </p>
            </div>
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