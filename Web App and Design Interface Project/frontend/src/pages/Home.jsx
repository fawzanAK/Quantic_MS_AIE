import { Link } from "react-router-dom";
import Newsletter from "../components/Newsletter";
import "./Home.css";

const QUICK_LINKS = [
  { to: "/menu", title: "Explore the Menu", desc: "Seasonal appetizers, entrées & desserts.", cta: "View Menu" },
  { to: "/reservations", title: "Reserve a Table", desc: "Pick a date, time and party size.", cta: "Book Now" },
  { to: "/gallery", title: "Gallery", desc: "A look inside the dining room & kitchen.", cta: "See Photos" },
];

const REVIEWS = [
  { stars: "★★★★★", quote: "The best tasting menu in the city — flawless service, unforgettable flavor.", source: "City Eats Magazine" },
  { stars: "★★★★★", quote: "An anniversary dinner we'll remember for years. Ask for the tasting menu.", source: "Google Review, J. Martins" },
  { stars: "🏆", quote: "2025 Award of Excellence — Fine Dining", source: "Wine & Table Guild" },
];

export default function Home() {
  return (
    <>
      <section className="hero">
        <div className="hero__overlay">
          <h1>Café Fausse</h1>
          <p>Contemporary Fine Dining, Rooted in Tradition</p>
          <div className="hero__actions">
            <Link to="/menu" className="btn-outline hero__outline">View Menu</Link>
            <Link to="/reservations" className="btn-primary">Reserve a Table</Link>
          </div>
        </div>
      </section>

      <section className="container intro">
        <p>
          Since 2010, Café Fausse has paired classic technique with seasonal, locally-sourced
          ingredients — an intimate dining room, an award-winning wine list, and a kitchen led by
          chefs who trained across Italy and France.
        </p>
      </section>

      <section className="container quick-links">
        {QUICK_LINKS.map((card) => (
          <div className="quick-links__card" key={card.to}>
            <div className="quick-links__icon" />
            <h3>{card.title}</h3>
            <p>{card.desc}</p>
            <Link to={card.to}>{card.cta} →</Link>
          </div>
        ))}
      </section>

      <section className="awards">
        <div className="container">
          <div className="awards__label">Awards &amp; Guest Reviews</div>
          <div className="awards__row">
            {REVIEWS.map((r) => (
              <div className="awards__card" key={r.source}>
                <div className="awards__stars">{r.stars}</div>
                <em>"{r.quote}"</em>
                <div className="awards__source">— {r.source}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="container newsletter-section">
        <h2>Stay in the Know</h2>
        <p>Seasonal menus, events &amp; offers — no spam.</p>
        <Newsletter />
      </section>
    </>
  );
}
