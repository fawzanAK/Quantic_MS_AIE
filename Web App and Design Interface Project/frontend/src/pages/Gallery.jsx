import { useState } from "react";
import "./Gallery.css";

// Real Café Fausse photography (provided image pack) mixed with curated
// royalty-free stock photos for slots the provided pack didn't cover.
const PHOTOS = [
  { id: 1, category: "Food", tile: "wide", src: "/images/gallery-ribeye-steak.webp" },
  { id: 2, category: "Interior", src: "/images/gallery-cafe-interior.webp" },
  { id: 3, category: "Ambiance", tile: "span2", src: "/images/gallery-special-event.webp" },
  { id: 4, category: "Food", src: "https://images.unsplash.com/photo-1550547660-d9450f859349?q=80&w=900&auto=format&fit=crop" },
  { id: 5, category: "Interior", tile: "wide", src: "/images/home-cafe-fausse.webp" },
  { id: 6, category: "Food", src: "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?q=80&w=900&auto=format&fit=crop" },
  { id: 7, category: "Ambiance", src: "https://images.unsplash.com/photo-1445019980597-93fa8acb246c?q=80&w=900&auto=format&fit=crop" },
  { id: 8, category: "Food", tile: "hero", src: "https://images.unsplash.com/photo-1504674900247-0877df9cc836?q=80&w=1200&auto=format&fit=crop" },
  { id: 9, category: "Interior", src: "https://images.unsplash.com/photo-1466637574441-749b8f19452f?q=80&w=900&auto=format&fit=crop" },
];

const FILTERS = ["All", "Food", "Interior", "Ambiance"];

export default function Gallery() {
  const [filter, setFilter] = useState("All");
  const [lightbox, setLightbox] = useState(null);

  const visible = filter === "All" ? PHOTOS : PHOTOS.filter((p) => p.category === filter);

  function openLightbox(index) {
    setLightbox(index);
  }
  function closeLightbox() {
    setLightbox(null);
  }
  function step(delta) {
    setLightbox((i) => (i + delta + visible.length) % visible.length);
  }

  return (
    <div className="gallery-page">
      <h1>Gallery</h1>

      <div className="gallery-page__filters">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`chip ${filter === f ? "chip--active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="gallery-grid container">
        {visible.map((photo, index) => (
          <button
            key={photo.id}
            className={`gallery-tile gallery-tile--${photo.tile || "default"}`}
            style={{ backgroundImage: `url(${photo.src})` }}
            onClick={() => openLightbox(index)}
            aria-label={`Open ${photo.category} photo`}
          />
        ))}
      </div>

      {lightbox !== null && (
        <div className="lightbox" onClick={closeLightbox}>
          <button className="lightbox__close" onClick={closeLightbox}>✕</button>
          <button className="lightbox__nav lightbox__nav--prev" onClick={(e) => { e.stopPropagation(); step(-1); }}>‹</button>
          <img
            src={visible[lightbox].src}
            alt={visible[lightbox].category}
            onClick={(e) => e.stopPropagation()}
          />
          <button className="lightbox__nav lightbox__nav--next" onClick={(e) => { e.stopPropagation(); step(1); }}>›</button>
        </div>
      )}

      <section className="gallery-awards container">
        <div className="gallery-awards__col">
          <h2>Awards</h2>
          <ul>
            <li>🏆 Culinary Excellence Award — 2022</li>
            <li>🏆 Restaurant of the Year — 2023</li>
            <li>🏆 Best Fine Dining Experience — Foodie Magazine, 2023</li>
          </ul>
        </div>
        <div className="gallery-awards__col">
          <h2>Guest Reviews</h2>
          <ul>
            <li>★★★★★ "Exceptional ambiance and unforgettable flavors." — Gourmet Review</li>
            <li>★★★★★ "A must-visit restaurant for food enthusiasts." — The Daily Bite</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
