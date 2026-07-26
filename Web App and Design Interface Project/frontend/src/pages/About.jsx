import "./About.css";

const TEAM = [
  {
    name: "Chef Antonio Rossi",
    role: "Founder & Executive Chef",
    bio: "Blends traditional Italian technique with modern culinary innovation; the creative force behind every seasonal menu.",
    avatarClass: "antonio",
  },
  {
    name: "Maria Lopez",
    role: "Founder & Restaurateur",
    bio: "Oversees the guest experience and Café Fausse's commitment to excellent, locally sourced ingredients.",
    avatarClass: "maria",
  },
];

const MILESTONES = [
  { year: "2010", label: "Founded by Antonio Rossi & Maria Lopez" },
  { year: "2022", label: "Culinary Excellence Award" },
  { year: "2023", label: "Restaurant of the Year" },
  { year: "2023", label: "Best Fine Dining Experience — Foodie Magazine" },
];

export default function About() {
  return (
    <div className="about-page">
      <section className="container about-story">
        <div className="about-story__text">
          <h1>About Café Fausse</h1>
          <p>
            Founded in 2010 by Chef Antonio Rossi and restaurateur Maria Lopez, Café Fausse blends
            traditional Italian flavors with modern culinary innovation. Our mission is to provide an
            unforgettable dining experience that reflects both quality and creativity — built on
            excellent food and locally sourced ingredients.
          </p>
        </div>
        <div className="about-story__photo" />
      </section>

      <section className="container about-team">
        <h2>Meet the Team</h2>
        <div className="about-team__grid">
          {TEAM.map((person) => (
            <div className="about-team__card" key={person.name}>
              <div className={`about-team__avatar about-team__avatar--${person.avatarClass}`} />
              <h3>{person.name}</h3>
              <div className="about-team__role">{person.role}</div>
              <p>{person.bio}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="milestones">
        <div className="container">
          <h2>Milestones</h2>
          <div className="milestones__row">
            {MILESTONES.map((m) => (
              <div className="milestones__item" key={m.year}>
                <span className="milestones__dot" />
                <div className="milestones__year">{m.year}</div>
                <div className="milestones__label">{m.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
