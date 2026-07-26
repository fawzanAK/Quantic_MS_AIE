import "./About.css";

const TEAM = [
  { name: "Marco Fausse", role: "Owner & Executive Chef", bio: "Trained in Lyon and Florence; 20 years in fine dining.", avatarClass: "marco" },
  { name: "Elena Ricci", role: "Co-Owner & Pastry Chef", bio: "Formerly of Le Bernardin; James Beard semifinalist.", avatarClass: "elena" },
  { name: "David Tran", role: "General Manager", bio: "Hospitality lead since the restaurant's opening in 2010.", avatarClass: "david" },
];

const MILESTONES = [
  { year: "2010", label: "Doors open" },
  { year: "2015", label: "First award" },
  { year: "2019", label: "Wine cellar expansion" },
  { year: "2025", label: "Award of Excellence" },
];

export default function About() {
  return (
    <div className="about-page">
      <section className="container about-story">
        <div className="about-story__text">
          <h1>Our Story</h1>
          <p>
            Café Fausse began in 2010 as a single dining room and a shared belief: that fine dining
            should feel warm, not formal. Fifteen years on, the same philosophy guides every plate —
            seasonal, honest, and built on relationships with local growers.
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
