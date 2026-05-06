const REPO_BASE = 'https://github.com/bsurya27/ai-research-curator/blob/main/';

// ─── L1 REGIONS ───────────────────────────────────────────────────────────
// Two overlapping dashed frames per the sketch:
//   Embedding Space — tall left frame wrapping recommender + taste profile.
//   Agentic Scraping Loop — wide top band that wraps BOTH the recommender
//     AND the web scraper, since the scraping loop runs through both.
const L1_REGIONS = [
  {
    id: 'scraping-loop',
    label: 'Agentic Scraping Loop',
    italic: true,
    labelAnchor: 'right',
    x: 80, y: 70, w: 1310, h: 200,
  },
  {
    id: 'embedding-space',
    label: 'Embedding Space',
    italic: true,
    labelAnchor: 'left',
    x: 55, y: 90, w: 420, h: 460,
  },
];

const L1_NODES = [
  // TOP-LEFT — inside embedding space
  {
    id: 'recommender',
    label: 'Recommender System',
    sublabel: 'Scores based on proximity',
    category: 'service',
    x: 235, y: 175, w: 250, h: 110,
  },
  // TOP-RIGHT — inside scraping loop
  {
    id: 'web',
    label: 'Web Scraper',
    sublabel: 'Scrapes items on order',
    category: 'external',
    x: 1150, y: 175, w: 240, h: 110,
  },
  // MID-LEFT — inside embedding space
  {
    id: 'taste_profile',
    label: 'Taste Profile',
    sublabel: 'User pref vector',
    category: 'storage',
    x: 215, y: 395, w: 220, h: 90,
  },
  // CENTER — the hub, dropped lower so arrows 3 / 4 / 5 don't collide
  {
    id: 'curator',
    label: 'Curation Agent',
    bullets: [
      'Samples pref vector',
      'Generates scrape queries',
      'Ranks + selects items',
      'Writes the daily personalized AI curation',
    ],
    category: 'agent',
    x: 720, y: 540, w: 300, h: 180,
  },
  // BOTTOM-LEFT — lowered slightly from before for breathing room
  {
    id: 'reporter',
    label: 'Reporter Agent',
    sublabel: "Processes user's feedback (implicit + explicit)",
    category: 'agent',
    x: 245, y: 740, w: 270, h: 110,
  },
  // BOTTOM-CENTER — directly below curator, fitting inside the 900-tall canvas
  {
    id: 'user',
    label: 'User',
    sublabel: 'Reads + reviews the curation',
    category: 'user',
    shape: 'person',
    x: 720, y: 820, w: 170, h: 140,
  },
];

// Ports on right edge of Embedding Space — ranked items leaves below the
// recommender (so its label clears "scraped items"), samples leaves aligned
// with curator y so the arrow is purely horizontal.
const EMBEDDING_PORT_5 = { x: 475, y: 540, w: 0, h: 0 };
const EMBEDDING_PORT_8 = { x: 475, y: 240, w: 0, h: 0 };

const STEPS = [
  {
    // Straight down from curator to user
    n: 1,
    label: 'latest ai curation',
    connection: 5,
    from: 'curator', to: 'user',
    route: 'v',
    labelPos: 'right',
    sum: 'Curator sends the finished daily briefing to the user.',
  },
  {
    // User → Reporter: go left then up to reporter's bottom
    n: 2,
    label: 'ratings + queries',
    connection: 7,
    from: 'user', to: 'reporter',
    route: 'h-v',
    labelPos: 'below',
    sum: 'User stars items and chats; all signals flow to the reporter.',
  },
  {
    // Reporter → Curator: go up then right. Shift +60 so this arrow attaches
    // to the LOWER part of the curator's left edge (no collision with #4 #5).
    n: 3,
    label: 'feedback signals',
    connection: 7,
    from: 'reporter', to: 'curator',
    route: 'v-h',
    labelPos: 'right',
    shift: 60,
    sum: 'Reporter forwards processed signals back to the curator.',
  },
  {
    // Curator → Taste Profile: go left then up. Shift -60 so this arrow leaves
    // the UPPER part of the curator's left edge (no collision with #3 #5).
    n: 4,
    label: 'updates pref vector',
    connection: 1,
    from: 'curator', to: 'taste_profile',
    route: 'h-v',
    labelPos: 'below',
    shift: -60,
    sum: 'Curator nudges the preference vector based on user reviews.',
  },
  {
    // Embedding space → Curator: horizontal samples line, lifted above
    // arrow 4 so the three left-edge arrows (4, 5, 3) read top → bottom.
    n: 5,
    label: 'samples',
    connection: 2,
    from: '_embedding_port_5', to: 'curator',
    route: 'h',
    labelPos: 'below',
    shift: -80,
    sum: 'Curator samples the taste profile to get cluster centroids.',
  },
  {
    // Curator → Web Scraper: go right then up
    n: 6,
    label: 'scraping queries',
    connection: 4,
    from: 'curator', to: 'web',
    route: 'h-v',
    labelPos: 'right',
    sum: 'Curator sends targeted queries to the web scraper.',
  },
  {
    // Web Scraper → Recommender: horizontal left across the top
    n: 7,
    label: 'scraped items',
    connection: 4,
    from: 'web', to: 'recommender',
    route: 'h',
    labelPos: 'above',
    sum: 'Web scraper returns raw items to the recommender for embedding.',
  },
  {
    // Embedding space → Curator: horizontal at recommender level, then down
    // to curator's top (ranked items leaves the embedding boundary, not the
    // recommender node).
    n: 8,
    label: 'ranked items',
    connection: 2,
    from: '_embedding_port_8', to: 'curator',
    route: 'h-v',
    labelPos: 'above',
    sum: 'Recommender scores items and returns ranked list to curator.',
  },
];

// ─── CONNECTIONS ───────────────────────────────────────────────────────────

// L2 layouts mirror L1 quadrants:
//   Embedding Space — LEFT (matches L1 embedding region on the left).
//   Curation Agent — RIGHT (matches L1 curator center-right of embedding).
//   Cross-references to the scraping scene — TOP-RIGHT (matches L1 web/Exa).
const CURATOR_CYCLE_L2 = {
  type: 'cycle',
  kicker: 'L2 · Curation Agent ↔ Embedding Space',
  title: 'Curation Agent ↔ Embedding Space',
  description:
    "The embedding space owns all of the recommendation math — the 1536-d preference vector, the KMeans clusters, and the embedded item store. The curator makes HTTP calls into it: push signals into the preference vector, sample clusters closest to that fresh preference, and ask for scraped items ranked by cosine similarity.",
  nodes: [
    { id: 'embedding', label: 'Embedding Space',
      sublabel: 'preference vector · KMeans clusters · item store',
      category: 'service', x: 370, y: 500, w: 440, h: 280 },
    { id: 'curator',   label: 'Curation Agent', category: 'agent',
      x: 1180, y: 500, w: 300, h: 280 },
    { id: 'ext_queries', shape: 'label', label: 'scraping queries  ⑥',
      category: 'external', x: 1180, y: 150, w: 240, h: 50 },
    { id: 'ext_items',   shape: 'label', label: 'new scraped items  ⑦',
      category: 'external', x: 370, y: 150, w: 240, h: 50 },
  ],
  arrows: [
    {
      id: 'a', stepNum: 4, connection: 1, from: 'curator', to: 'embedding',
      offset: 130, labelSide: 'above',
      caption: "Nudges the preference vector toward yesterday's liked items.",
      deep: {
        summary: 'Each rating dict is pushed into the recommender: URL, score, and source update the live 1536-d preference vector.',
        tech: 'HTTP to the embedding service; per-signal SGD-style nudge with |score - 3| * 0.05, then L2 normalize server-side.',
        vars: ['signal["url"]', 'signal["score"]', 'signal["source"]'],
        callLine: 'update_preference(signal["url"], signal["score"], signal["source"])',
        source: { file: 'curation_agent/curator.py', line: 256 },
      },
    },
    {
      id: 'b', stepNum: 5, connection: 2, from: 'embedding', to: 'curator',
      offset: 0, labelSide: 'above', labelW: 240,
      caption: 'Samples nearest cluster centroids.',
      deep: {
        summary: 'Pulls the current cluster layout over embedded items plus exemplar titles/URLs per centroid.',
        tech: 'HTTP GET to the recommender; k=3 clusters, up to five items shown per cluster.',
        vars: ['clusters_data', 'k', 'top_items', 'cluster_id', 'source_weights'],
        callLine: 'get_clusters(k=3, top_items=5)',
        source: { file: 'curation_agent/curator.py', line: 270 },
      },
    },
    { id: 'x6', stepNum: 6, connection: 4, clickLevel: 'L2',
      from: 'curator', to: 'ext_queries', context: true, dashed: true },
    { id: 'x7', stepNum: 7, connection: 4, clickLevel: 'L2',
      from: 'ext_items', to: 'embedding', context: true, dashed: true },
    {
      id: 'd', stepNum: 8, connection: 8, from: 'embedding', to: 'curator',
      offset: 130, labelSide: 'below',
      caption: "Returns the top-ranked items back to the curator.",
      deep: {
        summary: 'After scraped rows are embedded, this pass scores each dict against the user vector and returns sorted rows.',
        tech: 'Empty input short-circuits to []; post-filter drops non-positive scores before top_15 selection.',
        vars: ['all_scraped', 'scored', 'item["score"]'],
        callLine: 'score_items(all_scraped)',
        source: { file: 'curation_agent/curator.py', line: 418 },
      },
    },
  ],
};

// SCRAPING_CYCLE_L2 mirrors L1: curator CENTER, web scraper TOP-RIGHT,
//   today's new items in TOP-LEFT (where they head into the embedding region).
const SCRAPING_CYCLE_L2 = {
  type: 'cycle',
  kicker: 'L2 · Scrape new items',
  title: "Curation Agent → Web Scraper → Today's new items",
  description:
    "The curator takes its freshly-sampled clusters, reasons a query plan, and fans those queries out through the web scraper. Every returned item lands in a normalized schema, ready to be embedded and scored.",
  nodes: [
    { id: 'newitems', label: "Today's new items", shape: 'pages', category: 'data',
      x: 320, y: 200, w: 240, h: 140 },
    { id: 'web', label: 'Web Scraper', sublabel: 'powered by Exa search',
      category: 'external', x: 1280, y: 170, w: 220, h: 130 },
    { id: 'curator', label: 'Curation Agent', category: 'agent',
      x: 820, y: 540, w: 320, h: 130 },
    { id: 'clusters_in', shape: 'label', label: '← cluster samples  ⑤',
      category: 'external', x: 820, y: 800, w: 240, h: 50 },
  ],
  arrows: [
    {
      id: 'a', stepNum: 6, connection: 4, from: 'curator', to: 'web',
      labelSide: 'right', labelW: 320,
      caption: 'Reasons cluster-aware queries and runs each through the web scraper.',
      deep: {
        summary: "Claude turns cluster summaries plus weights into a list of {query, domains} specs that get fed into Exa one at a time.",
        tech: 'Each spec calls run_search(q, domains=domains); Exa returns results with optional domain filter and a recency cutoff.',
        vars: ['generated_queries', 'q', 'domains', 'items'],
        callLine: 'run_search(q, domains=domains)',
        source: { file: 'curation_agent/curator.py', line: 256 },
      },
    },
    {
      id: 'b', stepNum: 7, connection: 4, from: 'web', to: 'newitems',
      labelSide: 'below',
      caption: "Scraped results land in today's staging in normalized schema.",
      deep: {
        summary: 'Each result becomes one normalized dict (title, body, url, date, author, source) before dedupe.',
        tech: 'Source is inferred from the URL host (arxiv / reddit / twitter / generic); dedupe drops exact url collisions.',
        vars: ['raw vendor dict', 'inferred source'],
        callLine: 'normalize_item({...}, src)',
        source: { file: 'scraping/exa_scraper.py', line: 107 },
      },
    },
    { id: 'ctx5', stepNum: 5, connection: 2, clickLevel: 'L2',
      from: 'clusters_in', to: 'curator', context: true, dashed: true },
  ],
};

// REPORTER_CYCLE_L2 mirrors L1: curator TOP-CENTER, user BELOW curator,
//   reporter BOTTOM-LEFT (matching L1's reporter quadrant).
const REPORTER_CYCLE_L2 = {
  type: 'cycle',
  kicker: 'L2 · Daily briefing & feedback loop',
  title: 'Curator ↔ Reporter ↔ User',
  description:
    "The curator writes the daily editorial and hands it to the reporter, which renders it for the user. The user rates items and asks follow-up questions; the reporter funnels every signal back to the curator so tomorrow's run starts on sharper data.",
  nodes: [
    { id: 'curator', label: 'Curation Agent', category: 'agent',
      x: 820, y: 280, w: 320, h: 140 },
    { id: 'reporter', label: 'Reporter Agent', category: 'agent',
      x: 320, y: 720, w: 280, h: 140 },
    { id: 'user', label: 'User', shape: 'person', category: 'user',
      x: 820, y: 720, w: 200, h: 180 },
  ],
  arrows: [
    {
      id: 'briefing', stepNum: 1, connection: 5, from: 'curator', to: 'user',
      labelSide: 'right', labelW: 280,
      caption: "Writes the daily editorial and surfaces it via the reporter app.",
      deep: {
        summary: 'The curator persists briefing.md to the configured output path; the reporter Streamlit app reads it and renders the daily briefing for the user.',
        tech: 'Top items assembled earlier; this call writes the final editorial markdown (S3 or local).',
        vars: ['briefing_content', 'BRIEFING_OUTPUT_PATH'],
        callLine: 'write_briefing(briefing_content, BRIEFING_OUTPUT_PATH)',
        source: { file: 'curation_agent/curator.py', line: 465 },
      },
    },
    {
      id: 'ratings', stepNum: 2, connection: 7, from: 'user', to: 'reporter',
      labelSide: 'above', labelW: 240,
      caption: 'User rates every item and can chat about selected ones.',
      deep: {
        summary: 'Each star column writes one pipe-delimited line to signals with ISO timestamp.',
        tech: 'Streamlit reruns after each rating; URL and source come from the parsed briefing card.',
        vars: ['item["url"]', 'item["source"]', 'score', 'ts'],
        callLine: '_write_rating_signal(item["url"], item["source"], score)',
        source: { file: 'reporter/app.py', line: 817 },
      },
    },
    {
      id: 'feedback', stepNum: 3, connection: 7, from: 'reporter', to: 'curator',
      labelSide: 'above',
      caption: 'Writes rating signals and extracts more signals from chats via the LLM.',
      deep: {
        summary: 'Chat save runs Claude over the ASK transcript with URL allow-listing against briefing links.',
        tech: 'Star ratings use _write_rating_signal directly; chat path batches lines then calls _append_signals once.',
        vars: ['msgs', 'briefing', 'written', 'out_lines'],
        callLine: '_extract_signals(msgs, briefing, logger=logger)',
        source: { file: 'reporter/app.py', line: 688 },
      },
    },
  ],
};

const CONNECTIONS = [
  {
    number: 1,
    title: 'Update the preference vector',
    blurb: 'nudge pref vector · normalize',
    hosts: ['curator', 'taste_profile'],
    l2: CURATOR_CYCLE_L2,
  },
  {
    number: 2,
    title: 'Talk to the embedding space',
    blurb: 'sample clusters · rank scraped items',
    hosts: ['curator', 'recommender', 'taste_profile'],
    l2: CURATOR_CYCLE_L2,
  },
  {
    number: 3,
    title: 'Feedback signals to curator',
    blurb: 'reporter forwards processed signals back',
    hosts: ['reporter', 'curator'],
    l2: REPORTER_CYCLE_L2,
  },
  {
    number: 4,
    title: 'Scrape new items via Exa',
    blurb: 'fan out queries through Exa search',
    hosts: ['curator', 'web', 'recommender'],
    l2: SCRAPING_CYCLE_L2,
  },
  {
    number: 5,
    title: 'Deliver the daily briefing',
    blurb: 'write editorial markdown · deliver to user',
    hosts: ['curator', 'user'],
    l2: REPORTER_CYCLE_L2,
  },
  {
    number: 6,
    title: 'Scrape new items via Exa',
    blurb: 'fan out queries through Exa search',
    hosts: ['curator', 'web'],
    l2: SCRAPING_CYCLE_L2,
  },
  {
    number: 7,
    title: "Capture the user's review",
    blurb: 'star clicks · chat queries · extract signals · send to curator',
    hosts: ['user', 'reporter'],
    l2: REPORTER_CYCLE_L2,
  },
  {
    number: 8,
    title: 'Talk to the embedding space',
    blurb: 'ranked items back to curator',
    hosts: ['curator', 'recommender'],
    l2: CURATOR_CYCLE_L2,
  },
];

const L1_OVERVIEW = {
  title: 'A multi-agent loop for personal AI research',
  paragraph: "I built this small multi-agent system to break a familiar creative block — the loop of either doom-scrolling for inspiration or stalling in front of a blank page. Each morning a curation agent reads how I reacted to yesterday's picks, nudges a private 1536-d taste vector, asks the embedding space which clusters I'm closest to, and fans targeted scrape queries out to arXiv, Reddit, and Twitter. Everything that comes back gets scored against my taste vector; the top fifteen become a short, opinionated briefing. A reporter agent then renders that briefing in a Streamlit app, captures my star ratings and follow-up questions, and funnels those signals back so the next day's run trains on sharper data. Click any numbered step to see exactly which calls pass between which modules.",
};