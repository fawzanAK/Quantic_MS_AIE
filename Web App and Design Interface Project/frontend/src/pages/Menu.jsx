import { useEffect, useState } from "react";
import { fetchMenu } from "../api";
import "./Menu.css";

const FALLBACK_ORDER = ["Appetizers", "Entrees", "Desserts", "Beverages"];

export default function Menu() {
  const [menu, setMenu] = useState(null);
  const [activeCategory, setActiveCategory] = useState(FALLBACK_ORDER[0]);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchMenu()
      .then((data) => {
        if (data.ok === false) throw new Error("Failed to load menu");
        const { ok, status, ...categories } = data;
        setMenu(categories);
      })
      .catch(() => setError("Could not load the menu from the server. Showing may be incomplete."));
  }, []);

  const categories = menu ? Object.keys(menu) : FALLBACK_ORDER;

  function scrollTo(category) {
    setActiveCategory(category);
    document.getElementById(`menu-${category}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="menu-page">
      <h1 className="menu-page__title">Our Menu</h1>

      <div className="menu-page__chips">
        {categories.map((cat) => (
          <button
            key={cat}
            className={`chip ${activeCategory === cat ? "chip--active" : ""}`}
            onClick={() => scrollTo(cat)}
          >
            {cat}
          </button>
        ))}
      </div>

      {error && <p className="menu-page__error">{error}</p>}

      {!menu && !error && <p className="container">Loading menu…</p>}

      {menu &&
        categories.map((cat) => (
          <section className="container menu-category" id={`menu-${cat}`} key={cat}>
            <h2 className="menu-category__heading">{cat}</h2>
            <div className="menu-category__grid">
              {menu[cat].map((item) => (
                <div className="menu-item" key={item.name}>
                  <div className="menu-item__row">
                    <span>{item.name}</span>
                    <span>${item.price}</span>
                  </div>
                  <p>{item.description}</p>
                </div>
              ))}
            </div>
          </section>
        ))}
    </div>
  );
}
