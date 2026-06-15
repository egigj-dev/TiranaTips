import "./global.css";

// Tirana's international recognition — hardcoded editorial content. Slow-
// changing (a few entries a year), so a committed list is the right amount of
// engineering; each links to its primary source. Rendered as a bento grid in
// the "Tirana, seen globally" section.
const ACHIEVEMENTS = [
  {
    year: "2018",
    title: "European Prize for Urban Public Space",
    blurb:
      "Skanderbeg Square won Europe's top public-space award, beating 279 candidates from 32 countries for its pedestrian-first redesign.",
    href: "https://ruby-press.com/skanderbeg-square-by-51n4e-and-anri-sala-wins-european-prize-for-urban-public-space/",
    size: "large",
  },
  {
    year: "2023",
    title: "The Pyramid Reborn",
    blurb:
      "MVRDV transformed the communist-era Pyramid into a public creative hub, home to the TUMO Center for free tech education.",
    href: "https://www.mvrdv.com/projects/312/the-pyramid-of-tirana",
    size: "tall",
  },
  {
    year: "2022",
    title: "European Youth Capital",
    blurb:
      "Awarded the year-long title by the European Youth Forum, running 100+ events under the slogan \u201cActivate Youth.\u201d",
    href: "https://www.youthforum.org/news/congratulations-tirana-winner-of-the-european-youth-capital-for-2022",
    size: "small",
  },
  {
    year: "2024",
    title: "Lonely Planet Spotlight",
    blurb:
      "Featured in Lonely Planet's global travel guides, introducing Tirana to mainstream travelers.",
    href: "https://www.lonelyplanet.com/",
    size: "small",
  },
  {
    year: "2024",
    title: "Capital of Innovation Award",
    blurb:
      "Honored at the ANGI Awards in Rome for e-governance, smart infrastructure, and grassroots tech support.",
    href: "https://www.giovaniinnovatori.it/",
    size: "small",
  },
  {
    year: "2025",
    title: "Startup Ecosystem Growth",
    blurb:
      "Recorded +40.5% annual growth (StartupBlink), now the 32nd strongest startup environment in Eastern Europe.",
    href: "https://www.startupblink.com/startup-ecosystem/tirana-al",
    size: "wide",
  },
];

function Global() {
  return (
    <main className="global-page">
      <section className="global-hero">
        <div className="global-hero-content">
          <span className="global-hero-pill">Tirana, seen globally</span>
          <h1>A decade of recognition</h1>
          <p>
            Awards, transformations, and global attention that put Tirana on
            the world stage.
          </p>
        </div>
      </section>

      <section className="recognition-section">
        <ol className="recognition-timeline">
          {ACHIEVEMENTS.map((a) => (
            <li className="recognition-item" key={a.year + a.title}>
              <a
                className="recognition-node"
                href={a.href}
                target="_blank"
                rel="noreferrer"
                aria-label={`${a.year}: ${a.title}`}
              >
                <span className="hex">
                  <span className="hex-year">{a.year}</span>
                </span>
              </a>

              <a
                className="recognition-card"
                href={a.href}
                target="_blank"
                rel="noreferrer"
              >
                <h3>{a.title}</h3>
                <p>{a.blurb}</p>
                <span className="recognition-more">Read more →</span>
              </a>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}

export default Global;