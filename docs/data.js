// Architecture data.
// Two levels on the canvas:
//   L1: data-flow overview with numbered steps.
//   L2: zoom into a connection -- cycle arrows show operations; click an arrow to
//       dim the rest of the scene, read call-level notes, and open the exact
//       GitHub line for that call site.
//
// The LLM is not a module; it appears as prompts and API calls in the L2 notes.

const REPO_BASE = 'https://github.com/bsurya27/ai-research-curator/blob/main/';

// ─── L1 NODES ─────────────────────────────────────────────────────────────
// Layout follows the hand-drawn sketch: review + reporter on top, the main
// curator/briefing/user row in the middle, and web/scraped/embedding on the
// bottom. Plain-English labels.

const L1_NODES = [
  { id: 'review',    label: "User's review",    sublabel: 'of previous day briefing',
    category: 'storage', x: 510,  y: 130, w: 220, h: 96 },
  { id: 'reporter',  label: 'Reporter Agent',   category: 'agent',
    x: 1370, y: 130, w: 210, h: 96 },

  { id: 'web',       label: 'Web',              category: 'external',
    x: 130,  y: 430, w: 140, h: 80 },
  { id: 'curator',   label: 'Curation Agent',   category: 'agent',
    x: 620,  y: 430, w: 220, h: 96 },
  { id: 'briefing',  label: "Today's briefing", category: 'briefing', shape: 'pages',
    x: 1050, y: 430, w: 210, h: 112 },
  { id: 'user',      label: 'User',             category: 'user', shape: 'person',
    x: 1400, y: 430, w: 130, h: 112 },

  { id: 'scraped',   label: 'Scraped items',    category: 'storage', shape: 'pages',
    x: 130,  y: 740, w: 170, h: 96 },
  { id: 'embedding', label: 'Recommender',      sublabel: 'ranks items by taste',
    category: 'service', x: 640, y: 740, w: 240, h: 100 },
];

// ─── L1 STEPS ─────────────────────────────────────────────────────────────
// Ten numbered actions around the loop — the "story" of one daily run, in
// plain language. Each step owns its own arrow (from → to) so the chase
// highlight can light up the arrow, the number, and the label together.
// When multiple steps share the same pair of modules, their arrows are
// auto-offset in parallel so you can see each one individually.

const STEPS = [
  { n: 1,  label: 'reads review',           connection: 1, from: 'review',    to: 'curator',   labelPos: 'above',
    sum: "Opens yesterday's ratings file and parses every line." },
  { n: 2,  label: 'updates preferences',    connection: 2, from: 'curator',   to: 'embedding', labelPos: 'right',
    sum: "Nudges the taste vector toward things the user liked yesterday." },
  { n: 3,  label: 'samples what they like', connection: 2, from: 'embedding', to: 'curator',   labelPos: 'below',
    sum: 'Gets back a few clusters closest to the new taste vector.' },
  { n: 4,  label: 'scraping queries',       connection: 4, from: 'curator',   to: 'web',       labelPos: 'below',
    sum: 'Asks the LLM to turn those clusters into arxiv, reddit, and twitter queries, and runs them.' },
  { n: 5,  label: 'ranks by user history',  connection: 4, from: 'web',       to: 'embedding', labelPos: 'below',
    waypoint: 'scraped',
    sum: "Every scraped item is embedded and scored against the user's taste vector." },
  { n: 6,  label: 'top items for today',    connection: 2, from: 'embedding', to: 'curator',   labelPos: 'left',
    sum: "Pulls back the highest-scoring items for today's briefing." },
  { n: 7,  label: 'reasons how to present', connection: 5, from: 'curator',   to: 'briefing',  labelPos: 'above',
    sum: 'Asks the LLM to write a short editorial over the top picks, then saves it.' },
  { n: 8,  label: 'reads briefing',         connection: 6, from: 'briefing',  to: 'user',      labelPos: 'above',
    sum: 'The user opens the app and reads the rendered briefing.' },
  { n: 9,  label: 'ratings + chat queries', connection: 7, from: 'user',      to: 'reporter',  labelPos: 'left',
    sum: 'Stars, mark-read, and ASK-dialog chats all flow to the reporter app.' },
  { n: 10, label: 'new review',             connection: 7, from: 'reporter',  to: 'review',    labelPos: 'below',
    sum: "Signals from the session get appended to tomorrow's review file." },
];

// ─── CONNECTIONS ───────────────────────────────────────────────────────────
// Seven scenes — one per significant interaction. Each scene groups all the
// tool calls that happen across that connection.
// L2 for connection scenes is a two-party layout (left + right) with a
// vertical stack of labeled tool-arrows between them.
//
// Some related L1 steps collapse into a single, spacious L2 "cycle" scene
// (e.g. steps 8, 9, 10 → the reporter cycle). Those scenes use type:'cycle'
// and are shared by multiple CONNECTIONS so clicking any contributing step
// on L1 lands on the same L2.

const CURATOR_CYCLE_L2 = {
  type: 'cycle',
  kicker: 'L2 · Curation Agent ↔ Embedding Space',
  title: 'Curation Agent ↔ Embedding Space',
  description:
    "The embedding space owns all of the recommendation math — the 1536-d preference vector, the KMeans clusters, and the embedded item store. The curator just makes three HTTP calls into it: push yesterday's signals into the preference vector, sample clusters closest to that fresh preference, and ask for the freshly-scraped batch ranked by cosine similarity. Scraping itself (and what happens to new items before they're ranked) lives in other L2 scenes.",
  nodes: [
    { id: 'curator',   label: 'Curation Agent', category: 'agent',
      x: 900, y: 180, w: 320, h: 130 },
    { id: 'embedding', label: 'Embedding Space',
      sublabel: 'preference vector · KMeans clusters · item store',
      category: 'service', x: 900, y: 780, w: 480, h: 210 },

    { id: 'ext_queries', shape: 'label', label: 'scraping queries  →',
      category: 'external', x: 320, y: 180, w: 260, h: 50 },
    { id: 'ext_items',   shape: 'label', label: '←  new scraped items',
      category: 'external', x: 320, y: 780, w: 260, h: 50 },
  ],
  arrows: [
    {
      id: 'a', stepNum: 2, connection: 2, from: 'curator', to: 'embedding',
      offset: 120, labelSide: 'left',
      caption: "Nudges the preference vector toward yesterday's liked items.",
      details: [
        'POST /update  per signal',
        'SGD step  |score − 3| × 0.05',
        'L2-normalize  →  unit vector',
      ],
      deep: {
        summary:
          'Each rating dict from signals.txt is pushed into the recommender: URL, score, and source update the live 1536-d preference vector.',
        tech: 'HTTP to the embedding service; per-signal SGD-style nudge with |score - 3| * 0.05, then L2 normalize server-side.',
        vars: ['signal["url"]', 'signal["score"]', 'signal["source"]', 'result (dict or error payload)'],
        callLine: 'update_preference(signal["url"], signal["score"], signal["source"])',
        source: { file: 'curation_agent/curator.py', line: 256 },
      },
    },
    {
      id: 'b', stepNum: 3, connection: 2, from: 'embedding', to: 'curator',
      offset: 0, labelSide: 'below', labelW: 240, labelBg: true,
      caption: 'Samples nearest cluster centroids.',
      details: [
        'GET /clusters?k=3',
        'KMeans(6) over embeddings',
        'returns { clusters, weights }',
      ],
      deep: {
        summary:
          'Pulls the current cluster layout over embedded items plus exemplar titles/URLs per centroid, with source mixture weights.',
        tech: 'HTTP GET to the recommender; k=3 clusters, up to five items shown per cluster for query generation context.',
        vars: ['clusters_data', 'k', 'top_items', 'cluster_id', 'source_weights'],
        callLine: 'get_clusters(k=3, top_items=5)',
        source: { file: 'curation_agent/curator.py', line: 270 },
      },
    },
    { id: 'x4', stepNum: 4, connection: 4, clickLevel: 'L2',
      from: 'curator', to: 'ext_queries',
      context: true, dashed: true },
    { id: 'x5', stepNum: 5, connection: 4, clickLevel: 'L2',
      from: 'ext_items', to: 'embedding',
      context: true, dashed: true },

    {
      id: 'd', stepNum: 6, connection: 2, from: 'embedding', to: 'curator',
      offset: 120, labelSide: 'right',
      caption: "Returns the top-ranked items back to the curator for today's briefing.",
      details: [
        'sorted DESC by similarity score',
        "top 15  →  today's picks",
        '(reuses the /score response)',
      ],
      deep: {
        summary:
          'After scraped rows are embedded, this pass scores each dict against the user vector and returns sorted rows for the editorial step.',
        tech: 'Empty input short-circuits to []; post-filter drops non-positive scores before top_15 selection.',
        vars: ['all_scraped', 'scored', 'item["score"]'],
        callLine: 'score_items(all_scraped)',
        source: { file: 'curation_agent/curator.py', line: 418 },
      },
    },
  ],
};

// Layout mirrors L1: web sits LEFT of curator, scraped/newitems sits BELOW
// web, and the dotted peripheral lives BELOW curator in the slot where the
// Recommender sits at L1. The LLM is part of the agent's internals — it
// shows up in the arrow details as the prompt being used, not as its own box.
const SCRAPING_CYCLE_L2 = {
  type: 'cycle',
  kicker: 'L2 · Scrape new items',
  title: "Curation Agent → Web → Today's new items",
  description:
    "The curator takes its freshly-sampled clusters, reasons a per-source query plan (prompt: query_generation.txt), and fans those queries out across arXiv, Reddit, and Twitter, sleeping between calls to stay inside rate limits. Every returned item lands in today's staging in a normalized schema, ready to be embedded and scored against the user's taste vector.",
  nodes: [
    { id: 'curator', label: 'Curation Agent', category: 'agent',
      x: 900, y: 460, w: 320, h: 130 },
    { id: 'web', label: 'Web sources',
      sublabel: 'arxiv · reddit · twitter',
      category: 'external', x: 200, y: 460, w: 200, h: 130 },
    { id: 'newitems', label: "Today's new items",
      shape: 'pages', category: 'data',
      x: 200, y: 760, w: 240, h: 150 },
    { id: 'clusters_in', shape: 'label',
      label: '← cluster samples  ③',
      category: 'external', x: 900, y: 760, w: 240, h: 50 },
  ],
  arrows: [
    {
      id: 'a', stepNum: 4, connection: 4, from: 'curator', to: 'web',
      caption: 'Reasons per-source queries and runs every scraper.',
      details: [
        'prompt: query_generation.txt',
        'scrape_arxiv / scrape_reddit / scrape_twitter',
        'sleep 15s arxiv · 65s twitter',
      ],
      deep: {
        summary:
          'Warm path: Claude turns cluster summaries plus weights into per-source query lists. Cold start swaps in query_generation_cold_start.txt and keyword hints.',
        tech: 'Then the big for-source loop fans out scrape_arxiv / scrape_reddit / scrape_twitter with rate-limit sleeps and logging per query.',
        vars: ['generated_queries', 'cold_start', 'clusters_data', 'query_system', 'REDDIT_AVAILABLE_SUBREDDITS'],
        callLine: '_queries_from_claude(clusters_data, query_system, REDDIT_AVAILABLE_SUBREDDITS)',
        source: { file: 'curation_agent/curator.py', line: 308 },
      },
    },
    {
      id: 'b', stepNum: 5, connection: 4, from: 'web', to: 'newitems',
      labelSide: 'right', labelOffset: { dx: 100 },
      caption: "Items land in today's staging in normalized schema.",
      details: [
        'normalize_item(raw, source)',
        'title · body · url · date · source',
        'next: embed + score (step 5 → 6)',
      ],
      deep: {
        summary:
          'Scrapers normalize heterogeneous API payloads into one dict schema before dedupe and hand-off to embedding.',
        tech: 'Representative path: arXiv results become title/body/url/date/author/extra blobs keyed consistently for downstream embed_item.',
        vars: ['raw vendor dict', 'source string (e.g. "arxiv")'],
        callLine: 'normalize_item({...}, source="arxiv")',
        source: { file: 'scraping/arxiv_scraper.py', line: 69 },
      },
    },
    {
      id: 'ctx3', stepNum: 3, connection: 2, clickLevel: 'L2',
      from: 'clusters_in', to: 'curator',
      context: true, dashed: true,
    },
  ],
};

// Layout mirrors L1: briefing sits RIGHT of curator on the same row, and the
// dotted top_in peripheral lives BELOW curator in the Recommender slot. The
// LLM is part of the agent — its prompt shows up in the arrow details only.
const BRIEFING_CYCLE_L2 = {
  type: 'cycle',
  kicker: "L2 · Write today's briefing",
  title: 'Curation Agent → briefing.md',
  description:
    "Second reasoning step of the daily run. The curator takes the top-15 scored items and writes a short editorial over them (prompt: curation_and_writing.txt — locks the output to 5-8 mains with 2-4 sentence analyses plus a shorter 'Also worth a look' list). The rendered markdown lands in briefing.md, local file or S3 object, same adapter.",
  nodes: [
    { id: 'curator', label: 'Curation Agent', category: 'agent',
      x: 620, y: 460, w: 300, h: 130 },
    { id: 'briefing', label: 'briefing.md',
      sublabel: "today's picks · mains + also-worth",
      shape: 'pages', category: 'briefing',
      x: 1200, y: 460, w: 240, h: 160 },
    { id: 'top_in', shape: 'label',
      label: '← top-15 scored items  ⑥',
      category: 'external', x: 620, y: 760, w: 240, h: 50 },
  ],
  arrows: [
    {
      id: 'a', stepNum: 7, connection: 5, from: 'curator', to: 'briefing',
      labelW: 260,
      caption: "Writes a short editorial over the top picks, saved as briefing.md.",
      details: [
        'prompt: curation_and_writing.txt',
        'write_briefing(content, output_path)',
        'S3 PutObject · or local Path.write_text',
      ],
      deep: {
        summary:
          'Markdown from the curation LLM step is written to briefing.md (or S3) through the shared storage adapter.',
        tech: 'Top items were assembled earlier; this call persists the final editorial output path from the run configuration.',
        vars: ['briefing_content', 'BRIEFING_OUTPUT_PATH'],
        callLine: 'write_briefing(briefing_content, BRIEFING_OUTPUT_PATH)',
        source: { file: 'curation_agent/curator.py', line: 465 },
      },
    },
    {
      id: 'ctx6', stepNum: 6, connection: 2, clickLevel: 'L2',
      from: 'top_in', to: 'curator',
      context: true, dashed: true,
    },
  ],
};

const SIGNALS_CYCLE_L2 = {
  type: 'cycle',
  kicker: "L2 · Read yesterday's review",
  title: "signals.txt ↔ Curation Agent",
  description:
    "The first thing the curator does every run is drain signals.txt — the pipe-delimited log the reporter wrote yesterday. Each line becomes a {score, url, source, ts} dict; malformed lines are silently dropped. Once the full pipeline finishes successfully, the curator truncates the file so tomorrow's reporter starts from empty.",
  nodes: [
    { id: 'signals',  label: 'signals.txt', shape: 'pages', category: 'storage',
      sublabel: "yesterday's user review", x: 760, y: 260, w: 260, h: 160 },
    { id: 'curator',  label: 'Curation Agent',              category: 'agent',
      x: 760, y: 700, w: 320, h: 130 },
  ],
  arrows: [
    {
      id: 'a', stepNum: '1a', connection: 1, from: 'signals', to: 'curator',
      offset: 80, labelSide: 'left',
      caption: "Parses every line into a rating dict, silently drops malformed ones.",
      details: [
        'read_signals(path)',
        'score | url | source | ts',
        'returns list[{...}]',
      ],
      deep: {
        summary:
          'First call in run(): loads the pipe-delimited reporter log from local disk or S3 via the same storage adapter.',
        tech: 'Each valid line becomes a dict with score, url, source, ts; malformed rows are skipped without failing the run.',
        vars: ['signals (list[dict])', 'SIGNALS_PATH', 'logger'],
        callLine: 'read_signals(SIGNALS_PATH)',
        source: { file: 'curation_agent/curator.py', line: 250 },
      },
    },
    {
      id: 'b', stepNum: '1b', connection: 1, from: 'curator', to: 'signals',
      offset: 80, labelSide: 'right', dashed: true,
      caption: 'Truncates the file after the full pipeline succeeds.',
      details: [
        'clear_signals(path)',
        'fires once at run-end',
        'S3 or local — same adapter',
      ],
      deep: {
        summary:
          'After briefing write and optional SNS notify, the curator truncates signals so the next reporter session starts clean.',
        tech: 'Uses the shared signals adapter (local truncate or S3 overwrite) once the pipeline completes successfully.',
        vars: ['SIGNALS_PATH', 'logger'],
        callLine: 'clear_signals(SIGNALS_PATH)',
        source: { file: 'curation_agent/curator.py', line: 489 },
      },
    },
  ],
};

const REPORTER_CYCLE_L2 = {
  type: 'cycle',
  kicker: 'L2 · Reporter Agent cycle',
  title: 'Reporter Agent cycle',
  description:
    "Tail end of the daily loop. The reporter renders today's briefing for the user, watches what they do with it (ratings, mark-read, ASK-dialog chats), and funnels every signal into signals.txt so tomorrow's curator wakes up to fresh input.",
  // 2D layout — roughly matches the hand-drawn sketch. Bottom row is the
  // user-facing side (briefing → user); top row is the agent-facing side
  // (reporter → signals). Arrow 9 climbs up the right column to connect them.
  nodes: [
    { id: 'signals',  label: 'signals.txt',      shape: 'pages',  category: 'storage',  x: 340,  y: 260, w: 240, h: 160 },
    { id: 'reporter', label: 'Reporter Agent',                    category: 'agent',    x: 1160, y: 260, w: 280, h: 140 },
    { id: 'briefing', label: "Today's briefing", shape: 'pages',  category: 'briefing', x: 340,  y: 660, w: 240, h: 170 },
    { id: 'user',     label: 'User',             shape: 'person', category: 'user',     x: 1160, y: 660, w: 200, h: 180 },
  ],
  arrows: [
    {
      id: 'a', stepNum: 8, connection: 6, from: 'briefing', to: 'user',
      caption: 'Rendered on screen through the Streamlit app.',
      details: [
        'briefing.md (local or S3)',
        '_parse_briefing_md()',
        'main_items + also_items → card deck',
      ],
      deep: {
        summary:
          'Streamlit main loads raw markdown, splits mains vs also-worth sections, and seeds shown-item URLs plus fresh star widgets.',
        tech: 'Hash of raw briefing invalidates session ratings when the file changes behind the running app.',
        vars: ['raw', 'main_items', 'also_items', 'st.session_state.ratings'],
        callLine: 'main_items, also_items = _parse_briefing_md(raw or "")',
        source: { file: 'reporter/app.py', line: 744 },
      },
    },
    {
      id: 'b', stepNum: 9, connection: 7, from: 'user', to: 'reporter',
      caption: 'User rates every item and can chat about selected ones.',
      details: [
        'star click · mark read',
        'ASK dialog → conversation[]',
        'close session → unrated become score 2',
      ],
      deep: {
        summary:
          'Each star column writes one pipe-delimited line to signals.txt with ISO timestamp; unrated items default on session close.',
        tech: 'Streamlit reruns after each rating; URL and source come from the parsed briefing card.',
        vars: ['item["url"]', 'item["source"]', 'score', 'ts'],
        callLine: '_write_rating_signal(item["url"], item["source"], score)',
        source: { file: 'reporter/app.py', line: 817 },
      },
    },
    {
      id: 'c', stepNum: 10, connection: 7, from: 'reporter', to: 'signals',
      caption: 'Writes rating signals, and extracts more signals from chats via the LLM.',
      details: [
        '_write_rating_signal()',
        '_extract_signals() · LLM + URL allow-list',
        'append: score | url | source | ts',
      ],
      deep: {
        summary:
          'Chat save runs Claude over the ASK transcript with URL allow-listing against briefing links; parsed rows batch-append to signals.txt.',
        tech: 'Star ratings use _write_rating_signal directly; chat path batches lines then calls _append_signals once.',
        vars: ['msgs', 'briefing', 'written', 'out_lines'],
        callLine: '_extract_signals(msgs, briefing, logger=logger)',
        source: { file: 'reporter/app.py', line: 688 },
      },
    },
  ],
};

const CONNECTIONS = [

  // ═════ 1 ═════ signals ↔ curator ══════════════════════════════════════════
  {
    number: 1,
    title: "Read yesterday's review",
    blurb: 'parse the user\'s ratings · clear the file when done',
    marker: { x: 420, y: 460, labelBelow: true },
    hosts: ['signals', 'curator'],

    l2: SIGNALS_CYCLE_L2,
  },

  // ═════ 2 ═════ curator ↔ embedding space ══════════════════════════════════
  {
    number: 2,
    title: 'Talk to the embedding space',
    blurb: 'nudge preferences · sample clusters · embed new items · rank them',
    marker: { x: 620, y: 330, labelBelow: false },
    hosts: ['curator', 'embedding'],

    l2: CURATOR_CYCLE_L2,
  },

  // ═════ 3 ═════ curator internal reasoning: queries ════════════════════════
  {
    number: 3,
    title: 'Reason out search queries',
    blurb: 'LLM turns clusters + weights into per-source queries',
    marker: { x: 800, y: 500, labelBelow: true },
    hosts: ['curator'],

    l2: SCRAPING_CYCLE_L2,
  },

  // ═════ 4 ═════ curator ↔ scraping ═════════════════════════════════════════
  {
    number: 4,
    title: 'Scrape new items from the web',
    blurb: 'fan out queries to arxiv / reddit / twitter',
    marker: { x: 900, y: 380, labelBelow: false },
    hosts: ['curator', 'scraping'],

    l2: SCRAPING_CYCLE_L2,
  },

  // ═════ 5 ═════ curator → briefing.md (reasoning + write) ══════════════════
  {
    number: 5,
    title: 'Reason how to present the picks',
    blurb: 'LLM writes editorial markdown · save to briefing.md',
    marker: { x: 820, y: 620, labelBelow: true },
    hosts: ['curator', 'briefing'],

    l2: BRIEFING_CYCLE_L2,
  },

  // ═════ 6 ═════ briefing.md → reporter ═════════════════════════════════════
  {
    number: 6,
    title: 'Show the briefing to the user',
    blurb: 'read file · parse into cards · render in Streamlit',
    marker: { x: 690, y: 700, labelBelow: true },
    hosts: ['briefing', 'reporter'],

    l2: REPORTER_CYCLE_L2,
  },

  // ═════ 7 ═════ reporter ↔ user ↔ signals.txt ══════════════════════════════
  {
    number: 7,
    title: 'Capture the user\'s review',
    blurb: 'star clicks · chat queries · extract signals · append for tomorrow',
    marker: { x: 280, y: 700, labelBelow: true },
    hosts: ['user', 'reporter', 'signals'],

    l2: REPORTER_CYCLE_L2,
  },

];

const L1_OVERVIEW = {
  title: 'The daily loop',
  paragraph: 'One revolution of the system, told end-to-end. The curator reads yesterday\'s review, updates its idea of what the user likes, scrapes fresh items from the web, ranks them, and hands the top picks to the reporter as a briefing. The user reads the briefing, reacts, and the reporter writes a new review — which the curator will read tomorrow. Click any numbered step to see how it works under the hood.',
};
