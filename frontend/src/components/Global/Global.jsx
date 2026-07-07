import "./global.css";

import skylineImage from "../../assets/skyline.png";

// Tirana's international recognition — hardcoded editorial content. Slow-
// changing (a few entries a year), so a committed list is the right amount of
// engineering; each links to its primary source. Rendered as a bento grid in
// the "Tirana, seen globally" section.
// Images: real photos from Wikimedia Commons where the event has one
// (Skanderbeg Square, the Pyramid); themed Unsplash photos otherwise.
const ACHIEVEMENTS = [
  {
    year: "2018",
    title: "European Prize for Urban Public Space",
    blurb:
      "Skanderbeg Square won Europe's top public-space award, beating 279 candidates from 32 countries for its pedestrian-first redesign.",
    href: "https://ruby-press.com/skanderbeg-square-by-51n4e-and-anri-sala-wins-european-prize-for-urban-public-space/",
    image:
      "https://commons.wikimedia.org/wiki/Special:FilePath/Skanderbeg%20square%20(OSCAL19%20trip).jpg?width=900",
    imageAlt: "Skanderbeg Square in Tirana after its pedestrian redesign",
    size: "large",
  },
  {
    year: "2023",
    title: "The Pyramid Reborn",
    blurb:
      "MVRDV transformed the communist-era Pyramid into a public creative hub, home to the TUMO Center for free tech education.",
    href: "https://www.mvrdv.com/projects/312/the-pyramid-of-tirana",
    image:
      "https://commons.wikimedia.org/wiki/Special:FilePath/Pyramid%20of%20Tirana%20October%202023.jpg?width=900",
    imageAlt: "The renovated Pyramid of Tirana in 2023",
    size: "tall",
  },
  {
    year: "2022",
    title: "European Youth Capital",
    blurb:
      "Awarded the year-long title by the European Youth Forum, running 100+ events under the slogan \u201cActivate Youth.\u201d",
    href: "https://www.youthforum.org/news/congratulations-tirana-winner-of-the-european-youth-capital-for-2022",
    image:
      "https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?auto=format&fit=crop&w=900&q=80",
    imageAlt: "Young crowd at an open-air event",
    size: "small",
  },
  {
    year: "2024",
    title: "Lonely Planet Spotlight",
    blurb:
      "Featured in Lonely Planet's global travel guides, introducing Tirana to mainstream travelers.",
    href: "https://www.lonelyplanet.com/",
    image:
      "https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=900&q=80",
    imageAlt: "Travel map and camera laid out for planning a trip",
    size: "small",
  },
  {
    year: "2024",
    title: "Capital of Innovation Award",
    blurb:
      "Honored at the ANGI Awards in Rome for e-governance, smart infrastructure, and grassroots tech support.",
    href: "https://www.giovaniinnovatori.it/",
    image:
      "https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=900&q=80",
    imageAlt: "City skyline lit up at night",
    size: "small",
  },
  {
    year: "2025",
    title: "Startup Ecosystem Growth",
    blurb:
      "Recorded +40.5% annual growth (StartupBlink), now the 32nd strongest startup environment in Eastern Europe.",
    href: "https://www.startupblink.com/startup-ecosystem/tirana-al",
    image:
      "https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=900&q=80",
    imageAlt: "Team collaborating in a co-working space",
    size: "wide",
  },
];

function Global() {
  return (
    <main className="global-page">
      <section className="global-hero">
        <img
          className="global-hero-skyline"
          src={skylineImage}
          alt=""
          aria-hidden="true"
        />

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
                <span className="recognition-thumb">
                  <img src={a.image} alt={a.imageAlt} loading="lazy" />
                </span>

                <div className="recognition-body">
                  <h3>{a.title}</h3>
                  <p>{a.blurb}</p>
                  <span className="recognition-more">Read more →</span>
                </div>
              </a>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}

export default Global;