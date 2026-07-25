import { useState } from "react";
import { NavLink } from "react-router-dom";
import "./Header.css";

const NAV_LINKS = [
  { to: "/", label: "Home" },
  { to: "/menu", label: "Menu" },
  { to: "/reservations", label: "Reservations" },
  { to: "/about", label: "About" },
  { to: "/gallery", label: "Gallery" },
];

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="site-header">
      <div className="site-header__row container">
        <NavLink to="/" className="site-header__brand" onClick={() => setMenuOpen(false)}>
          CAFÉ FAUSSE
        </NavLink>

        <nav className={`site-header__nav ${menuOpen ? "is-open" : ""}`}>
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => (isActive ? "is-active" : "")}
              onClick={() => setMenuOpen(false)}
            >
              {link.label}
            </NavLink>
          ))}
          <NavLink to="/reservations" className="btn-primary site-header__cta-mobile" onClick={() => setMenuOpen(false)}>
            Reserve a Table
          </NavLink>
        </nav>

        <NavLink to="/reservations" className="btn-primary site-header__cta">
          Reserve a Table
        </NavLink>

        <button
          className="site-header__toggle"
          aria-label="Toggle navigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          ☰
        </button>
      </div>
    </header>
  );
}
