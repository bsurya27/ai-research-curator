// Architecture data.
// Three levels:
//   L1: data-flow overview with 7 numbered connections (not steps).
//   L2: zoom into a CONNECTION — shows every operation that travels across it.
//   L3: the actual tool/function cards with inline code snippets.
//
// The LLM is not a module — it's a swappable tool that shows up inside L3 code.

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
    },
    {
      id: 'b', stepNum: 9, connection: 7, from: 'user', to: 'reporter',
      caption: 'User rates every item and can chat about selected ones.',
      details: [
        'star click · mark read',
        'ASK dialog → conversation[]',
        'close session → unrated become score 2',
      ],
    },
    {
      id: 'c', stepNum: 10, connection: 7, from: 'reporter', to: 'signals',
      caption: 'Writes rating signals, and extracts more signals from chats via the LLM.',
      details: [
        '_write_rating_signal()',
        '_extract_signals() · LLM + URL allow-list',
        'append: score | url | source | ts',
      ],
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

    l3: {
      description: 'Both tools live in the curator\'s thin storage-adapter layer. They transparently branch between local-file and S3 so the rest of the pipeline never sees a path.',
      tools: [
        {
          name: 'read_signals(path)',
          brief: 'Parse signals.txt into validated signal dicts.',
          file: 'curation_agent/tools.py',
          code: `def read_signals(signals_path: str) -> list[dict]:
    """Read signals.txt, return list of {score, url, source, timestamp}."""
    if _is_s3():
        obj = _s3_client().get_object(Bucket=S3_BUCKET, Key="signals.txt")
        content = obj["Body"].read().decode("utf-8")
    else:
        content = Path(signals_path).read_text(encoding="utf-8")

    out = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 4:
            continue
        try:
            score = float(parts[0])
        except ValueError:
            continue
        out.append({"score": score, "url": parts[1],
                    "source": parts[2], "timestamp": parts[3]})
    return out`,
        },
        {
          name: 'clear_signals(path)',
          brief: 'Truncate signals.txt to empty after the run succeeds.',
          file: 'curation_agent/tools.py',
          code: `def clear_signals(signals_path: str) -> None:
    """Clear signals.txt after processing."""
    if _is_s3():
        _s3_client().put_object(
            Bucket=S3_BUCKET, Key="signals.txt", Body=b""
        )
    else:
        p = Path(signals_path)
        if p.is_file():
            p.write_text("", encoding="utf-8")`,
        },
      ],
    },
  },

  // ═════ 2 ═════ curator ↔ embedding space ══════════════════════════════════
  {
    number: 2,
    title: 'Talk to the embedding space',
    blurb: 'nudge preferences · sample clusters · embed new items · rank them',
    marker: { x: 620, y: 330, labelBelow: false },
    hosts: ['curator', 'embedding'],

    l2: CURATOR_CYCLE_L2,

    l3: {
      description: 'All four client-side tools are thin HTTP wrappers. The real logic lives in the rec_model service — each endpoint has a corresponding Python module that owns one responsibility.',
      tools: [
        {
          name: 'update_preference(url, score, source)',
          brief: 'POST /update. Server does SGD nudge: step = |score−3| × 0.05.',
          file: 'curation_agent/tools.py',
          code: `def update_preference(url, score, source) -> dict:
    """POST /update to rec model."""
    r = httpx.post(
        f"{REC_MODEL_URL}/update",
        json={"url": url, "source": source, "score": score},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()`,
        },
        {
          name: 'get_clusters(k, top_items)',
          brief: 'GET /clusters. Returns k closest clusters with top_items reps each.',
          file: 'curation_agent/tools.py',
          code: `def get_clusters(k: int = 3, top_items: int = 5) -> dict:
    """GET /clusters from rec model."""
    r = httpx.get(
        f"{REC_MODEL_URL}/clusters",
        params={"k": k, "top_items": top_items},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()`,
        },
        {
          name: 'embed_item(title, body, url, source, date)',
          brief: 'POST /embed. The write to Chroma is the point — return is ignored.',
          file: 'curation_agent/tools.py',
          code: `def embed_item(title, body, url, source, date) -> dict:
    """POST /embed to rec model."""
    r = httpx.post(
        f"{REC_MODEL_URL}/embed",
        json={"title": title, "body": body, "url": url,
              "source": source, "date": date},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()`,
        },
        {
          name: 'score_items(items)',
          brief: 'POST /score with the whole batch. One OpenAI call, returns sorted DESC.',
          file: 'curation_agent/tools.py',
          code: `def score_items(items: list[dict]) -> list[dict]:
    """POST /score to rec model. Returns sorted by score DESC."""
    payload = [
        {"title": i.get("title", ""),
         "body":  i.get("body", ""),
         "url":   i.get("url", ""),
         "source":i.get("source", ""),
         "date":  str(i.get("date", ""))}
        for i in items
    ]
    r = httpx.post(
        f"{REC_MODEL_URL}/score",
        json={"items": payload},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["items"]`,
        },
        {
          name: 'preference.update(pref, item, signal)',
          brief: 'Server-side. SGD step toward item on like, away on dislike, then unit-normalize.',
          file: 'rec_model/preference.py',
          code: `def update_preference(current, item_embedding, signal,
                      step_size=0.1):
    """Move preference toward (like) or away from (dislike) an item."""
    item = np.asarray(item_embedding, dtype=np.float64).reshape(-1)
    cur  = np.asarray(current, dtype=np.float64).reshape(-1)
    if signal == "like":
        new = cur + step_size * (item - cur)
    else:
        new = cur - step_size * (item - cur)
    return _unit(new)`,
        },
        {
          name: 'cluster.fit_and_rank(pref, k)',
          brief: 'Server-side. KMeans(6) over all embeddings, cosine-rank centroids against preference.',
          file: 'rec_model/cluster.py',
          code: `km = KMeans(n_clusters=6, n_init=10, random_state=42)
km.fit(embeddings)

sims = [cosine_similarity(pref, c)
        for c in km.cluster_centers_]
top_k = np.argsort(-np.array(sims))[:k]

for c in top_k:
    members = [e for e, lbl in zip(embeddings, km.labels_)
               if lbl == c]
    dists = [np.linalg.norm(e - km.cluster_centers_[c])
             for e in members]`,
        },
      ],
    },
  },

  // ═════ 3 ═════ curator internal reasoning: queries ════════════════════════
  {
    number: 3,
    title: 'Reason out search queries',
    blurb: 'LLM turns clusters + weights into per-source queries',
    marker: { x: 800, y: 500, labelBelow: true },
    hosts: ['curator'],

    l2: SCRAPING_CYCLE_L2,

    l3: {
      description: 'The LLM client is a dependency — swap the model name and provider at the top of curator.py. The prompt file is the real contract.',
      tools: [
        {
          name: '_queries_from_claude(clusters, prompt)',
          brief: 'Send cluster JSON to the LLM. Retry on overload. Return parsed queries JSON.',
          file: 'curation_agent/curator.py',
          code: `def _queries_from_claude(clusters_data, system_prompt, ...):
    payload = {
        "clusters": clusters_data.get("clusters", []),
        "source_weights": clusters_data.get("source_weights", {}),
        "reddit_available_subreddits": reddit_subreddit_catalog,
    }
    user_text = json.dumps(payload, indent=2) + _QUERY_JSON_INSTRUCTIONS

    client = anthropic.Anthropic(api_key=...)
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            )
            break
        except Exception as e:
            if "529" in str(e):
                time.sleep(2 ** attempt * 5)
                continue
            raise
    return _parse_json_object(msg.content[0].text)`,
        },
        {
          name: '_is_cold_start()',
          brief: 'If item_count < 50, use the cold-start prompt driven by onboarding keywords.',
          file: 'curation_agent/curator.py',
          code: `def _is_cold_start() -> bool:
    try:
        health = httpx.get(
            f"{REC_MODEL_URL}/health", timeout=10.0
        ).json()
        return int(health.get("item_count", 0)) < 50
    except Exception:
        return False`,
        },
      ],
    },
  },

  // ═════ 4 ═════ curator ↔ scraping ═════════════════════════════════════════
  {
    number: 4,
    title: 'Scrape new items from the web',
    blurb: 'fan out queries to arxiv / reddit / twitter',
    marker: { x: 900, y: 380, labelBelow: false },
    hosts: ['curator', 'scraping'],

    l2: SCRAPING_CYCLE_L2,

    l3: {
      description: 'The curator\'s tools.py exposes thin wrappers over each source module. The actual Apify polling, rate-limit handling, and schema normalization all live in scraping/.',
      tools: [
        {
          name: 'scrape_arxiv(query)',
          brief: 'Overfetch by 3× then trim to days_back for recency. Abstract becomes body.',
          file: 'curation_agent/tools.py',
          code: `def scrape_arxiv(query: str,
                 max_results: int = 25,
                 days_back: int = 7) -> list[dict]:
    """Wrapper around search_arxiv."""
    return search_arxiv(query,
                        max_results=max_results,
                        days_back=days_back)`,
        },
        {
          name: 'scrape_reddit(subreddits)',
          brief: 'Apify actor on a subreddit listing. Polls until SUCCEEDED or TIMED_OUT.',
          file: 'curation_agent/tools.py',
          code: `def scrape_reddit(subreddits: list[str],
                  max_results: int = 20,
                  days_back: int = 1) -> list[dict]:
    """Wrapper around scrape_subreddits."""
    return scrape_subreddits(
        subreddits=subreddits,
        max_results=max_results,
        days_back=days_back,
    )`,
        },
        {
          name: 'scrape_twitter(query)',
          brief: 'Apify altimis/scweet actor, Latest sort. Tweet first 80 chars → title.',
          file: 'curation_agent/tools.py',
          code: `def scrape_twitter(query: str,
                   max_results: int = 25,
                   days_back: int = 4) -> list[dict]:
    """Wrapper around search_twitter."""
    return search_twitter(query,
                          max_results=max_results,
                          days_back=days_back)`,
        },
        {
          name: 'normalize_item(raw, source)',
          brief: 'The schema enforcer. Every scraper pipes through this.',
          file: 'scraping/utils.py',
          code: `SCHEMA_KEYS = ("title", "body", "url", "date",
               "author", "source", "extra")

def normalize_item(raw: dict, source: str) -> dict:
    out = {k: raw.get(k, "") for k in SCHEMA_KEYS}
    out["source"] = source
    out["extra"]  = raw.get("extra", {})
    return out`,
        },
      ],
    },
  },

  // ═════ 5 ═════ curator → briefing.md (reasoning + write) ══════════════════
  {
    number: 5,
    title: 'Reason how to present the picks',
    blurb: 'LLM writes editorial markdown · save to briefing.md',
    marker: { x: 820, y: 620, labelBelow: true },
    hosts: ['curator', 'briefing'],

    l2: BRIEFING_CYCLE_L2,

    l3: {
      description: 'Two tools in sequence — the LLM produces the markdown, then write_briefing handles the local/S3 persistence.',
      tools: [
        {
          name: '_briefing_from_claude(top_15, prompt)',
          brief: 'Hand top-15 to the LLM with the curation_and_writing prompt. Return markdown string.',
          file: 'curation_agent/curator.py',
          code: `def _briefing_from_claude(top_15, system_prompt) -> str:
    user_text = (
        "Items JSON:\\n"
        + json.dumps({"items": top_15}, indent=2)
        + "\\n\\nWrite a markdown briefing for the reader. "
        + "Use headings and links where appropriate."
    )
    client = anthropic.Anthropic(api_key=...)
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            )
            break
        except Exception as e:
            if "529" in str(e):
                time.sleep(2 ** attempt * 5); continue
            raise
    return msg.content[0].text`,
        },
        {
          name: 'write_briefing(content, output_path)',
          brief: 'Persist markdown. S3 → PutObject; local → Path.write_text (mkdir parents).',
          file: 'curation_agent/tools.py',
          code: `def write_briefing(content: str, output_path: str) -> None:
    """Save briefing markdown to output_path."""
    if _is_s3():
        _s3_client().put_object(
            Bucket=S3_BUCKET, Key="briefing.md",
            Body=content.encode("utf-8"),
        )
    else:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")`,
        },
      ],
    },
  },

  // ═════ 6 ═════ briefing.md → reporter ═════════════════════════════════════
  {
    number: 6,
    title: 'Show the briefing to the user',
    blurb: 'read file · parse into cards · render in Streamlit',
    marker: { x: 690, y: 700, labelBelow: true },
    hosts: ['briefing', 'reporter'],

    l2: REPORTER_CYCLE_L2,

    l3: {
      description: 'Parsing is regex-based and strict — which is why the writing prompt on the curator side locks the output structure.',
      tools: [
        {
          name: '_read_briefing_raw()',
          brief: 'Fetch briefing.md from local or S3. Returns None if missing.',
          file: 'reporter/app.py',
          code: `def _read_briefing_raw() -> str | None:
    if _is_s3():
        try:
            obj = _s3_client().get_object(
                Bucket=S3_BUCKET, Key="briefing.md"
            )
            return obj["Body"].read().decode("utf-8")
        except Exception:
            return None
    p = Path(BRIEFING_PATH)
    return p.read_text(encoding="utf-8") if p.is_file() else None`,
        },
        {
          name: '_parse_briefing_md(md)',
          brief: 'Split on "Also worth a look"; regex-extract ### headings and bullet links.',
          file: 'reporter/app.py',
          code: `_HEADING  = re.compile(r"^###\\s+\\[([^\\]]+)\\]\\((https?://[^\\)]+)\\)\\s*$")
_TAG_LINE = re.compile(r"^\\s*\\[(reddit|arxiv|twitter|devto)\\]\\s*$", re.I)

def _parse_briefing_md(md: str) -> tuple[list[dict], list[dict]]:
    parts = re.split(r"^##\\s+also worth a look.*$",
                     md, flags=re.I | re.M, maxsplit=1)
    main_md = parts[0]
    also_md = parts[1] if len(parts) > 1 else ""

    main_items = _parse_main_items(main_md)
    also_items = _parse_also_items(also_md)
    return main_items, also_items`,
        },
      ],
    },
  },

  // ═════ 7 ═════ reporter ↔ user ↔ signals.txt ══════════════════════════════
  {
    number: 7,
    title: 'Capture the user\'s review',
    blurb: 'star clicks · chat queries · extract signals · append for tomorrow',
    marker: { x: 280, y: 700, labelBelow: true },
    hosts: ['user', 'reporter', 'signals'],

    l2: REPORTER_CYCLE_L2,

    l3: {
      description: 'Five tools cooperate. Three are trivial wrappers; two do real work: _extract_signals (LLM + URL validation) and _parse_briefing_md (regex).',
      tools: [
        {
          name: '_write_rating_signal(url, source, score)',
          brief: 'Append a single pipe-delimited rating line on every star click.',
          file: 'reporter/app.py',
          code: `def _write_rating_signal(url, source, score) -> None:
    ts = datetime.utcnow().isoformat() + "Z"
    line = f"{score} | {url} | {source} | {ts}\\n"
    _append_signals([line])`,
        },
        {
          name: '_append_signals(lines)',
          brief: 'Append a batch to signals.txt. S3-aware: read, concat, PutObject.',
          file: 'reporter/app.py',
          code: `def _append_signals(lines: list[str]) -> None:
    if not lines:
        return
    text = "".join(lines)
    if _is_s3():
        try:
            obj = _s3_client().get_object(
                Bucket=S3_BUCKET, Key="signals.txt"
            )
            existing = obj["Body"].read().decode("utf-8")
        except Exception:
            existing = ""
        _s3_client().put_object(
            Bucket=S3_BUCKET, Key="signals.txt",
            Body=(existing + text).encode("utf-8"),
        )
    else:
        with open(SIGNALS_PATH, "a", encoding="utf-8") as f:
            f.write(text)`,
        },
        {
          name: '_extract_signals(messages, briefing, logger)',
          brief: 'Send chat + briefing to LLM, parse pipe-delimited response, drop neutrals + hallucinated URLs, append.',
          file: 'reporter/app.py',
          code: `def _extract_signals(messages, briefing_content, logger):
    briefing_urls = _urls_from_briefing(briefing_content)
    convo = _format_conversation(messages)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        system=SIGNAL_EXTRACTION_PROMPT,
        messages=[{"role": "user",
                   "content": f"{briefing_content}\\n\\n{convo}"}],
    )
    out_lines = []
    for line in resp.content[0].text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        score, url, source, ts = parts[:4]
        if float(score) == 3.0:
            continue
        if not _url_allowed(url, briefing_urls):
            continue
        out_lines.append(f"{score} | {url} | {source} | {ts}\\n")
    _append_signals(out_lines)`,
        },
        {
          name: '_urls_from_briefing(text)',
          brief: 'Allow-list of URLs from the current briefing. Blocks LLM-hallucinated links.',
          file: 'reporter/app.py',
          code: `def _urls_from_briefing(text: str) -> set[str]:
    urls = set()
    for match in re.finditer(r"\\((https?://[^\\)]+)\\)", text):
        urls.add(match.group(1).strip())
    return urls

def _url_allowed(url: str, briefing_urls: set[str]) -> bool:
    return url.strip() in briefing_urls`,
        },
      ],
    },
  },

];

const L1_OVERVIEW = {
  title: 'The daily loop',
  paragraph: 'One revolution of the system, told end-to-end. The curator reads yesterday\'s review, updates its idea of what the user likes, scrapes fresh items from the web, ranks them, and hands the top picks to the reporter as a briefing. The user reads the briefing, reacts, and the reporter writes a new review — which the curator will read tomorrow. Click any numbered step to see how it works under the hood.',
};
