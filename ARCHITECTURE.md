# Architecture

A reference for understanding what this project is, how the pieces fit together, and what to expect when reading the code.

---

## 1. What This Project Is

An automated, personalized AI/ML research briefing system.

Every day it scrapes papers, Reddit posts, and tweets, ranks them against a learned preference vector unique to the user, asks Claude to write an editorial briefing, and serves it via a Streamlit reading UI. The user reads, rates items, and chats with Claude about the briefing — those interactions produce preference signals that continuously improve the ranking.

It is a closed feedback loop: **read → rate → rank better → read again.**

No model training, no labels, no offline pipeline. The user's taste is represented as a single L2-normalized vector in the same 1536-d embedding space as the content, nudged online via SGD-style updates from implicit feedback.

---

## 2. Top-Level Component Map

```
┌────────────────┐    one-time     ┌──────────────────────────────────────┐
│  onboarding/   │ ─────────────►  │          Storage Layer               │
│    app.py      │                 │  (local files  OR  AWS S3 bucket)    │
└────────────────┘                 │                                      │
                                   │  preference.npy   (1536-d unit vec)  │
┌────────────────┐  daily cron     │  cold_start.json  (seed keywords)    │
│  curation_     │ ─────────────►  │  source_weights.json                 │
│  agent/        │                 │  signals.txt      (pipe-delimited)   │
│  curator.py    │                 │  briefing.md      (markdown output)  │
└───────┬────────┘                 │  chroma/          (vector DB)        │
        │                          │  logs/            (JSON run logs)    │
        │ HTTP (localhost:8000)    └──────────────────────────────────────┘
        ▼
┌────────────────┐
│   rec_model/   │   FastAPI service (runs in background all day)
│    app.py      │   /embed  /score  /update  /clusters  /health
└────────────────┘
        │
        ├── embedder.py      OpenAI text-embedding-3-small (1536-d)
        ├── vector_store.py  ChromaDB persistent collection
        ├── preference.py    NumPy .npy preference vector (online update)
        ├── cluster.py       KMeans over all stored embeddings
        └── scorer.py        Cosine similarity vs preference vector

┌────────────────┐
│   reporter/    │   Streamlit UI (read briefing, rate, chat)
│    app.py      │ ──────────────► writes back to signals.txt
└────────────────┘

┌────────────────┐
│   scraping/    │   arxiv, Apify reddit/twitter, dev.to (+ unused/ legacy)
└────────────────┘
```

---

## 3. Directory Layout

```
ai-research-curator/
├── .env.example                # Template for environment variables
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt            # All Python dependencies
├── startup.sh                  # EC2 daily boot script
├── shutdown.sh                 # EC2 shutdown + S3 backup + self-terminate
├── .vscode/
│   └── settings.json
│
├── onboarding/
│   └── app.py                  # One-time Streamlit setup for preference vector
│
├── curation_agent/             # Agent 1 — daily pipeline orchestrator
│   ├── curator.py              # 11-step daily pipeline
│   ├── tools.py                # Thin HTTP wrappers around rec_model + scrapers
│   ├── logger.py               # RunLogger — structured JSON run logs
│   └── prompts/
│       ├── query_generation.txt              # Normal mode prompt for Claude
│       ├── query_generation_cold_start.txt   # Cold-start prompt for Claude
│       └── curation_and_writing.txt          # Briefing writer prompt
│
├── rec_model/                  # Recommendation model (FastAPI service)
│   ├── __init__.py             # (empty)
│   ├── app.py                  # FastAPI routes: /embed /score /update /clusters /health
│   ├── embedder.py             # OpenAI text-embedding-3-small (1536-d)
│   ├── vector_store.py         # ChromaDB persistent collection
│   ├── preference.py           # Preference vector load/save/update
│   ├── cluster.py              # KMeans + closest cluster selection
│   ├── scorer.py               # Cosine similarity scoring
│   ├── test_endpoints.py       # httpx smoke tests of all endpoints
│   └── test_modules.py         # embedder + vector_store module tests
│
├── reporter/                   # Agent 2 — reading UI
│   ├── app.py                  # Streamlit briefing UI + chat + star ratings
│   ├── logger.py               # ReporterLogger
│   └── prompts/
│       └── signal_extraction.txt             # Chat → signals extraction prompt
│
├── scraping/                   # Content scrapers (shared normalized schema)
│   ├── __init__.py             # Exports active scrapers
│   ├── utils.py                # normalize_item(), deduplicate()
│   ├── arxiv_scraper.py        # search_arxiv() via arxiv library
│   ├── apify_reddit_scraper.py # search_reddit() + scrape_subreddits() via Apify
│   ├── apify_twitter_scraper.py# search_twitter() via Apify
│   ├── devto_scraper.py        # search_devto() + get_top_devto() via Dev.to API
│   └── unused/                 # Legacy scrapers, kept for reference
│       ├── hackernews_scraper.py
│       ├── lobsters_scraper.py
│       ├── paperswithcode_scraper.py
│       ├── reddit_scraper.py   # (PRAW, superseded by Apify)
│       └── twitter_scraper.py  # (twscrape, superseded by Apify)
│
└── experiments/
    └── embedding_exp_1/        # Offline comparison of embedding models
        ├── collect_data.py
        ├── label_data.py
        ├── deduplicate.py
        ├── run_experiments.py
        ├── plot_embeddings.py
        └── embedding_exp1_results.csv
```

The following paths are gitignored and created at runtime:
`curation_agent/data/` (signals.txt, briefing.md), `rec_model/data/` (preference.npy, source_weights.json, chroma/), `reporter/data/`, `logs/`, `experiments/embedding_exp_1/data/`, `experiments/embedding_exp_1/models/`.

---

## 4. Data Model — What Flows Through the System

### 4.1 Normalized scraped item

Every scraper returns a list of dicts with the same shape (enforced by `scraping/utils.py::normalize_item`):

```
{
  "title":  str,              # Title or first 80 chars of tweet
  "body":   str,              # Abstract / selftext / tweet body / article body
  "url":    str,              # Canonical URL — used as dedup key
  "date":   str,              # ISO-8601, or "" if invalid
  "author": str,
  "source": str,              # "arxiv" | "reddit" | "twitter" | "devto"
  "extra":  dict,             # Source-specific: arxiv {categories,pdf_url},
                              #   reddit {score,num_comments,subreddit},
                              #   twitter {likes,retweets,views},
                              #   devto {tags,reactions,comments,reading_time}
}
```

### 4.2 Embedded item (in ChromaDB)

```
item_id    = MD5(url)                          # hex string — primary key
embedding  = list[float] length 1536           # OpenAI text-embedding-3-small
metadata   = {title, body (≤500 chars), url, source, date}
```

### 4.3 Preference vector

A single NumPy float64 array of shape `(1536,)`, L2-normalized to unit length. Stored as `preference.npy`.

### 4.4 Source weights

```
source_weights.json
{
  "arxiv":   float,
  "reddit":  float,
  "twitter": float,
  "devto":   float
}
```

Values are renormalized so the four weights sum to **4.0** after every update.

### 4.5 Signals file

`signals.txt` — append-only, pipe-delimited, one signal per line:

```
score | url | source | timestamp
```

- `score` is a float 1–5. Score 3 = neutral and is silently discarded downstream.
- `url` must match a URL the curator has previously embedded.
- `timestamp` is ISO-8601 UTC.
- Lines starting with `#` or missing fields are ignored.

### 4.6 Briefing

`briefing.md` — markdown output from Claude. Structure expected by the reporter parser:

```
(optional opener)

### [Title](https://...)
2-4 sentence summary.
[arxiv]                    ← optional inline source tag

### [Next Title](...)
...

## Also worth a look
- [Link title](https://...) — one-line note
- [Another](https://...) — note
```

---

## 5. Module-by-Module Reference

### 5.1 `onboarding/app.py` — One-Time Setup

**Purpose:** Run once before first use to bootstrap the user's preference vector.

**Flow:**
1. Streamlit renders 12 fixed keyword checkboxes (e.g. "Large Language Models", "Agentic AI Systems", "Vision Language Models").
2. User picks 3–5 topics and clicks Initialize.
3. `embed_batch(selected_keywords)` → single OpenAI call returning 1536-d vectors.
4. Element-wise mean → L2-normalize → save to `preference.npy`.
5. Save the original keyword strings to `cold_start.json` with a timestamp.

**Outputs:**
- `preference.npy` — initial semantic taste direction
- `cold_start.json` — `{keywords: [...], initialized_at: "..."}` — the curator reads this in cold-start mode

---

### 5.2 `rec_model/` — Recommendation Model (FastAPI Service)

Long-running HTTP service on `localhost:8000`. Started by `startup.sh` before the curator runs. Owns all ML state. Other components never touch ChromaDB or `preference.npy` directly — they go through this API.

#### `embedder.py` — Text Embedding

- Model: OpenAI `text-embedding-3-small`, dimension **1536**
- `clean_text(title, body)` — strips fenced code blocks, removes `# * _ \` > ` chars, collapses whitespace, truncates body to 600 chars, combines as `"title. body"`.
- `embed_text(text) -> list[float]` — single-item embed.
- `embed_batch(texts) -> list[list[float]]` — batched embed in a single API call. Order-preserving.

A Sentence Transformers (`all-MiniLM-L6-v2`, dim=384) alternative is commented out at the bottom of the file for use without OpenAI.

#### `vector_store.py` — ChromaDB Persistence

- Persistent collection named `"content"` at `CHROMA_PERSIST_DIR` (default `rec_model/data/chroma/`).
- **ID scheme:** `MD5(url)` — this enforces deduplication across pipeline runs at the vector store level.
- `store_item(id, embedding, metadata)` — idempotent; skips silently if id exists.
- `get_all_embeddings() -> (ids, embeddings, metadatas)` — full collection dump for clustering.
- Lazy singleton client/collection initialization.

#### `preference.py` — Preference Vector

| Function | Behavior |
|---|---|
| `_unit(v)` | L2-normalize, raises on zero vector |
| `load_preference(dim)` | Load from local file or S3; if missing, returns a **random unit vector** |
| `save_preference(vector)` | Write to local file or S3 object |
| `update_preference(current, item_embedding, signal, step_size)` | Online update rule (below), returns unit vector |

**Update rule:**
- `"like"` (score > 3): `new = current + step_size * (item - current)`
- `"dislike"` (score < 3): `new = current - step_size * (item - current)`
- Always re-normalized to unit length.
- `step_size = abs(score - 3.0) * 0.05` → score 5 or 1 produces step 0.1; score 4 or 2 produces step 0.05.

Score 3 (neutral) is rejected earlier in `POST /update` and never reaches this function.

#### `cluster.py` — KMeans Helpers

- `fit_clusters(embeddings, n_clusters=6)` — fits `sklearn.KMeans(n_init=10, random_state=42)`. Clamps `k` down to `n_samples` when tiny.
- `get_closest_clusters(preference, kmeans, k=3)` — ranks centroids by **cosine similarity** to preference, returns top-k indices.
- `get_top_items_per_cluster(cluster_idx, kmeans, ids, embeddings, metadatas, top_k=5)` — items in that cluster sorted by **Euclidean distance** to the centroid, ascending.

Cosine is used for preference↔centroid ranking; Euclidean is used for within-cluster item ranking.

#### `scorer.py` — Scoring

- `cosine_similarity(a, b) -> float` (returns 0 on zero norms)
- `score_items(items, preference)` — adds a `"score"` key to each item that has an `"embedding"`, sorts descending. Items missing an embedding are dropped with a warning.

#### `app.py` — FastAPI Routes

All routes serialize errors via a generic handler that returns `{detail: "Internal server error"}` with HTTP 500.

**`POST /embed`** — Body: `{title, body, url, source, date}`
Cleans text, embeds, stores in Chroma. Idempotent by `MD5(url)`. Returns `{item_id, embedded: bool}`.

**`POST /score`** — Body: `{items: [EmbedBody, ...]}`
Cleans all item texts, calls `embed_batch` (single OpenAI call), scores against preference, sorts. Returns items with `score` appended (embedding stripped from response).

**`POST /update`** — Body: `{url, source, score}`
1. If `score ≈ 3.0`, returns `{updated: false, skipped: true, reason: "neutral"}`.
2. Looks up the item's embedding in Chroma by `MD5(url)`; returns HTTP 404 if not found.
3. `load_preference` → `update_preference` → `save_preference`.
4. Updates source weight: like → ×1.05, dislike → ×0.95, then renormalizes all four weights to sum to 4.0.

**`GET /clusters?k=3&top_items=5`**
- Requires ≥6 items in Chroma (else returns empty list with a `message`).
- `get_all_embeddings` → `fit_clusters(n_clusters=6)` → `get_closest_clusters(k=3)` → `get_top_items_per_cluster(top_k=5)` per cluster.
- Response: `{clusters: [{cluster_id, items: [{title, body, url, source}]}, ...], source_weights: {...}}`.

**`GET /health`**
Returns `{status: "ok", item_count: <chroma count>}`. The curator uses `item_count < 50` as the cold-start trigger.

---

### 5.3 `scraping/` — Content Scrapers

All active scrapers return `list[dict]` matching the normalized schema from §4.1.

| Scraper | Backend | Key function | Defaults |
|---|---|---|---|
| `arxiv_scraper.py` | `arxiv` Python library | `search_arxiv(query, max_results=20, days_back=7)` | Over-fetches 3× then filters by `days_back` |
| `apify_reddit_scraper.py` | Apify `automation-lab/reddit-scraper` | `search_reddit(query, max_results=20, days_back=7)`, `scrape_subreddits(subreddits, max_results=20, days_back=1)` | 5-min poll timeout, 3s poll interval |
| `apify_twitter_scraper.py` | Apify `altimis/scweet` | `search_twitter(query, max_results=20, days_back=3, min_likes=0)` | `search_sort="Latest"`, same poll pattern |
| `devto_scraper.py` | Dev.to public API (no auth) | `search_devto(query, ...)`, `get_top_devto(tag, ...)` | 0.5s sleep between article body fetches |

**Apify flow** (shared by Reddit and Twitter):
1. `POST /v2/acts/{actor}/runs` with input payload → receive `run_id`.
2. Poll `GET /v2/acts/{actor}/runs/{run_id}` every 3 seconds (max 5 minutes) until status is `SUCCEEDED|FAILED|ABORTED|TIMED-OUT`.
3. On success, fetch results from `GET /v2/datasets/{defaultDatasetId}/items`.

**Curator-level rate limiting** (in `curator.py`, not in the scrapers themselves):
- 15s sleep between arxiv queries.
- 65s sleep between twitter queries (except after the last one).
- No explicit sleep between reddit queries (Apify queues them).

**Note:** Dev.to is exported from `scraping/__init__.py` but is **not called** by the current curator pipeline. It is available for future use.

---

### 5.4 `curation_agent/` — Daily Pipeline

#### `tools.py` — Adapter Layer

Thin wrapper with three responsibilities:
1. **HTTP client** to rec_model: `read_signals`, `update_preference`, `get_clusters`, `embed_item`, `score_items`, `write_briefing`, `clear_signals`.
2. **Scraping adapters:** `scrape_arxiv`, `scrape_reddit`, `scrape_twitter`, `search_reddit_query`.
3. **Storage routing:** `read_signals` and `write_briefing` transparently switch between local and S3 based on `STORAGE_BACKEND`.

Global constant: `REC_MODEL_URL = "http://localhost:8000"`, `TIMEOUT = 60.0`.

#### `curator.py` — The 11-Step Pipeline

Driven by `run()` at the bottom of the file. Every step logs to `RunLogger`.

**Step 1 — Read signals** (`read_signals(SIGNALS_PATH)`)
Returns list of `{score, url, source, timestamp}` parsed from `signals.txt`.

**Step 2 — Update preference** (`POST /update` per signal)
Rec model looks up each URL's embedding in Chroma, nudges preference, updates source weights. Signals for URLs not in Chroma return 404 and are logged as errors without aborting the run.

**Step 3 — Get clusters** (`GET /clusters?k=3&top_items=5`)
Returns 3 clusters (closest to current preference) each with 5 representative items, plus current source weights.

**Step 4 — Query generation (Claude)**

Cold-start detection uses `GET /health`: `item_count < 50` → cold-start mode.

- **Normal:** prompt `prompts/query_generation.txt`. Context JSON = `{clusters, source_weights, message, reddit_available_subreddits}`. Source-weight guidance in the prompt: weight > 1.2 → 3-4 queries; weight < 0.8 → 1-2 queries.
- **Cold start:** prompt `prompts/query_generation_cold_start.txt`. Context JSON = `{user_interests: [keywords_from_cold_start.json], reddit_available_subreddits}`. Budget: 2-3 arxiv / 1-2 reddit / 1-2 twitter per interest.

Both use `claude-sonnet-4-20250514`, max_tokens=4096. Normal path has exponential-backoff retry (5s, 10s, 20s) on 529 overloaded errors.

Expected Claude JSON output:
```json
{
  "arxiv":  ["query1", "query2", ...],
  "reddit": {"subreddits": ["SubName", ...], "queries": ["..."]},
  "twitter":["query1", ...]
}
```

`_normalize_reddit_queries_value` also accepts legacy `reddit: [list of strings]` and normalizes it.

Structural rules enforced by the prompts:
- No standalone acronyms (expand LLM, RAG, VLM, PEFT, etc.)
- ArXiv queries must start with `(cat:cs.LG OR cat:cs.AI OR cat:cs.CL OR cat:cs.CV OR cat:cs.IR) AND ...`
- Reddit queries should read like forum posts, not paper titles
- Twitter queries should be short and conversational

**Step 5 — Scrape**

Iterates over `generated_queries`:
- `arxiv` queries → `scrape_arxiv(query)` → sleep 15s
- `reddit`:
  - `scrape_reddit(chosen_subs or REDDIT_SUBREDDITS)` on subreddit listings
  - Then each keyword query → `search_reddit_query(q)`
  - (`REDDIT_SUBREDDITS` default = `["MachineLearning", "LocalLLaMA", "artificial"]`; Claude picks from `REDDIT_AVAILABLE_SUBREDDITS` = 8-entry catalog)
- `twitter` queries → `scrape_twitter(query)` → sleep 65s (except after last)

All items collected into `all_scraped: list[dict]`.

**Step 6 — Embed** (`POST /embed` per item, then `deduplicate(all_scraped)` on URL)
Rec model stores new items in Chroma (duplicates skipped by MD5). Python-side dedup is also applied to keep the downstream score request clean.

**Step 7 — Score** (`POST /score` with all deduplicated items)
Rec model batch-embeds all items in a single OpenAI call, scores via cosine similarity to preference, returns sorted descending. Curator drops items with `score ≤ 0`.

**Step 8 — Briefing generation (Claude)**
- Input: top 15 scored items.
- Prompt: `prompts/curation_and_writing.txt` (persona = "Surya's research companion", editorial tone, markdown structure).
- Model: `claude-sonnet-4-20250514`, max_tokens=8192, same retry policy.

**Step 9 — Write briefing** (`write_briefing(content, BRIEFING_OUTPUT_PATH)`)
Writes `briefing.md` to local file or S3 object.

**Step 9b — SNS notification** (S3 mode only)
Publishes to `SNS_TOPIC_ARN`: "Your research briefing is ready".

**Step 10 — Clear signals** (`clear_signals(SIGNALS_PATH)`)
Truncates `signals.txt` to empty so the next run doesn't re-process today's signals.

**Step 11 — Upload run log to S3** (S3 mode only)
Uploads the RunLogger JSON to `s3://{bucket}/logs/{date}_{run_id[:8]}.json`.

#### `logger.py` — RunLogger

Writes `logs/curation_agent/{YYYY-MM-DD}_{run_id[:8]}.json`. Every `.log(step, data)` call appends an entry with `{run_id, step, timestamp, data}` and immediately re-serializes the whole file (not buffered). Every pipeline step writes at least one entry (and errors are logged with `_error` suffix).

---

### 5.5 `reporter/app.py` — Streamlit Reading UI

Launch: `streamlit run reporter/app.py`.

#### Briefing parser (`_parse_briefing_md`)

Splits the markdown at the first `## Also worth a look` heading.

- **Main items:** found via regex `^### \[Title\]\(URL\)$`. Everything between one heading and the next is the summary. If the last line of the summary is `[arxiv]` / `[reddit]` / `[twitter]` / `[devto]`, it's consumed as the source override (otherwise inferred from URL domain).
- **Also items:** bullet lines under the "Also worth a look" section with `[title](url)` pattern.

#### UI

- Custom dark editorial theme (Playfair Display for headings, DM Sans for body, gold `#c9a96e` accent).
- Top bar: title + today's date.
- "Sources" strip shows current source weights as block characters: `SOURCES · arxiv ████████ · reddit ████░░░░ · twitter ██░░░░░░`.
- Each main item rendered as a `.re-card` with source badge, title link (opens in new tab), and summary.
- **Star rating** (1–5 via 5 buttons) per item. Clicking immediately appends one line to `signals.txt` and `st.rerun()`s.
- **Mark read** button — equivalent to score 2.
- **Also worth a look** section below as compact cards.
- **Close session** — assigns score=2 to every main item not already rated, appends all to `signals.txt`, then freezes the UI on a "Session saved. See you tomorrow." message.
- **Floating ASK button** — opens a chat dialog (see below).

#### ASK chat dialog (`_chat_dialog`)

- `@st.dialog` modal with a full Claude chat interface.
- Model: `claude-haiku-4-5-20251001`, max_tokens=4096.
- System prompt embeds the entire current briefing.
- Multi-turn conversation stored in `st.session_state.messages`.
- Two exit buttons:
  - **Save signals & close** → calls `_extract_signals(messages, briefing)` (see below).
  - **Close without saving** → discards the conversation.

#### Signal extraction (`_extract_signals`)

Prompt: `reporter/prompts/signal_extraction.txt`.

1. Send Claude the briefing markdown + the full conversation transcript.
2. Claude responds with pipe-delimited lines: `score | url | source | timestamp`.
3. Filter: score 3 (neutral) dropped; URLs validated against the set extracted from the briefing markdown (`_urls_from_briefing`) — any URL not present in the briefing is rejected.
4. Appended to `signals.txt`.

All chat turns, system prompts, and extracted signals are captured via `ReporterLogger` into `logs/reporter/{date}_{run_id[:8]}.json`.

---

### 5.6 `startup.sh` / `shutdown.sh` — EC2 Orchestration

**`startup.sh`** (run on EC2 boot, e.g. via EventBridge + SSM):

1. `cd` into project, `chmod +x` both scripts.
2. `git pull origin main`.
3. Export `.env`.
4. If `rec_model/data/chroma/` doesn't exist locally, restore from `s3://{bucket}/chroma.tar.gz` (or start fresh).
5. Pull latest `APIFY_API_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` from AWS SSM Parameter Store and overwrite `.env` via `sed`.
6. `source venv/bin/activate`.
7. Start `rec_model/app.py` via `nohup` in the background, log to `/tmp/rec_model.log`.
8. Poll `http://localhost:8000/health` every 2s (up to 60s) until it responds.
9. `python curation_agent/curator.py` (blocking).
10. Call `shutdown.sh`.

**`shutdown.sh`:**

1. `tar -czf /tmp/chroma.tar.gz` the chroma dir and `aws s3 cp` it to `s3://{bucket}/chroma.tar.gz`.
2. `pkill -f "python rec_model/app.py"`.
3. Fetch instance metadata via IMDSv2 token, then `aws ec2 stop-instances --instance-ids $INSTANCE_ID` — the instance self-terminates.

This design makes the EC2 instance **ephemeral**: it boots, runs the daily pipeline, backs up Chroma to S3, self-stops. Persistent state lives entirely in S3.

---

### 5.7 `experiments/embedding_exp_1/` — Research Experiment (Not Production)

Standalone offline comparison of embedding models for this use case.

| File | Purpose |
|---|---|
| `collect_data.py` | Multi-source JSONL collection with checkpointing |
| `label_data.py` | Streamlit UI for manually labeling similarity pairs |
| `deduplicate.py` | Dedupe the labeled dataset by URL |
| `run_experiments.py` | Evaluate OpenAI small/large, Voyage, SPECTER2 on labeled pairs |
| `plot_embeddings.py` | UMAP visualizations of each model's embedding space |
| `embedding_exp1_results.csv` | Results table — `openai-small` selected for balance of quality and cost |

This module is orthogonal to the live system; nothing in `curator.py` or `rec_model/` depends on it.

---

## 6. End-to-End Data Flow

```
FIRST RUN (onboarding, once)
────────────────────────────

user picks 3-5 topics
      │
      ▼
onboarding/app.py
      │ embed_batch(keywords)
      ▼
OpenAI API → 1536-d vectors
      │ mean → L2-normalize
      ▼
preference.npy + cold_start.json ─────► storage (local or S3)


DAILY PIPELINE (startup.sh → curator.py)
─────────────────────────────────────────

signals.txt (from yesterday's reading)
      │
      ▼
[Step 1] read_signals()
      │   [{score, url, source, ts}, ...]
      ▼
[Step 2] POST /update × N
      │   rec_model: MD5(url) → Chroma lookup → nudge preference.npy
      │               update source_weights.json
      ▼
[Step 3] GET /clusters
      │   KMeans(n=6) over entire Chroma store
      │   3 clusters closest to preference
      │   5 representative items per cluster
      ▼
[Step 4] Claude (sonnet-4) with cluster JSON + source weights
      │   or cold-start prompt if item_count < 50
      │   → {arxiv:[], reddit:{subreddits,queries}, twitter:[]}
      ▼
[Step 5] Scrape
      │   arxiv (15s sleep between queries)
      │   reddit subs + search queries (Apify)
      │   twitter (65s sleep between queries, Apify)
      │   → all_scraped: list[normalized dict]
      ▼
[Step 6] POST /embed × all_scraped
      │   clean_text → embed_text → store in Chroma (MD5 idempotent)
      │   + python-side deduplicate() by URL
      ▼
[Step 7] POST /score
      │   embed_batch (1 OpenAI call) → cosine(emb, preference)
      │   sorted desc, filter score > 0
      ▼
[Step 8] Claude (sonnet-4) with top 15 items
      │   writes markdown briefing (editorial tone)
      ▼
[Step 9]  write briefing.md → storage
[Step 9b] SNS notification (S3 mode only)
[Step 10] clear signals.txt
[Step 11] upload run log → S3


USER READS BRIEFING (reporter/app.py, any time after pipeline)
──────────────────────────────────────────────────────────────

briefing.md (from storage)
      │
      ▼
_parse_briefing_md → main_items + also_items
      │
      ├─► Star rating (1–5) → "{score} | {url} | {source} | {ts}\n" → signals.txt
      │
      ├─► Mark read → score 2 → signals.txt
      │
      ├─► Close session → score 2 for all unrated → signals.txt
      │
      └─► ASK chat (claude-haiku-4-5)
              │  multi-turn, briefing in system prompt
              │
              ▼  (on "Save signals & close")
          _extract_signals: Claude reads conversation + briefing
          → pipe-delimited signals → filter neutral/unknown URLs
          → append to signals.txt

(next morning: Step 1 of the pipeline reads these signals → loop closes)
```

---

## 7. External Services and Secrets

Defined in `.env` (see `.env.example`):

| Service | Purpose | Keys |
|---|---|---|
| OpenAI | Embeddings (`text-embedding-3-small`) | `OPENAI_API_KEY` |
| Anthropic | Query generation, briefing, chat, signal extraction | `ANTHROPIC_API_KEY` |
| Apify | Reddit + Twitter scraping actors | `APIFY_API_TOKEN` |
| AWS S3 | Shared state when `STORAGE_BACKEND=s3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET` |
| AWS SNS (optional) | "Briefing ready" notification | `SNS_TOPIC_ARN` |
| AWS SSM (prod only) | Pull secrets on EC2 boot | instance profile role |
| Reddit | (unused, legacy PRAW scraper only) | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` |
| Twitter cookies | (unused, legacy twscrape only) | `TWITTER_AUTH_TOKEN`, `TWITTER_CT0` |
| Voyage AI | Experiments only | `VOYAGE_API_KEY` |

Models used:
- Embeddings: OpenAI `text-embedding-3-small` (1536-d)
- Query generation + briefing: Claude `claude-sonnet-4-20250514`
- Chat + signal extraction: Claude `claude-haiku-4-5-20251001`

Storage toggle: `STORAGE_BACKEND=local` (default) or `STORAGE_BACKEND=s3`. All code paths that touch `signals.txt`, `briefing.md`, `preference.npy`, `source_weights.json`, `cold_start.json` branch on this.

---

## 8. Key Design Decisions

**Preference as a single unit vector.** No training, no labels. Online SGD-style updates in embedding space. Scoring is just a dot product. This keeps the system dependency-light and inspection-friendly.

**MD5(url) as the vector store primary key.** Free deduplication across pipeline runs with no extra bookkeeping. The rec model's `/update` endpoint requires items to be embedded first — the URL is the handshake between the reporter and the vector store.

**Source weights as a parallel signal.** Beyond per-item preference, each source has a drift weight. Claude uses this to allocate queries; the reporter shows it as a visual bar. Weights always renormalize to sum to 4.0 (one per source).

**Cold start detected at runtime.** Not a config flag — the curator asks rec_model how many items are stored. Below 50, it switches to the cold-start prompt with keywords from `cold_start.json`. Transparent to the user.

**ChromaDB, tarred to S3 between runs.** Chroma runs entirely local to the EC2 instance. `shutdown.sh` backs it up to S3; `startup.sh` restores on next boot. No always-on database infrastructure.

**`signals.txt` as the cross-process interface.** Pipe-delimited append-only file. The reporter writes, the curator reads and clears. No queue, no DB, no socket. Survives all the failure modes you can think of.

**Apify replaced PRAW + twscrape.** The legacy scrapers live in `scraping/unused/` for reference. Apify handles auth, rate limits, and browser automation, which eliminated a large maintenance surface.

**Two Claude tiers.** Sonnet for quality-critical tasks (query generation, briefing writing). Haiku for interactive tasks (chat, signal extraction) where latency and cost dominate.

**Ephemeral EC2 as daily cron.** The instance boots, runs the pipeline, backs up Chroma, self-stops. Cost is minutes of compute per day. The only always-on infra is S3 (and optionally the reporter on Hugging Face Spaces).

---

## 9. Where to Look First When Reading the Code

If you have 15 minutes and want to understand the system, read in this order:

1. `curation_agent/curator.py` — top-level flow, end to end (~500 lines)
2. `rec_model/app.py` — the five HTTP endpoints and what they call
3. `rec_model/preference.py` — the update rule, 130 lines, the mathematical heart
4. `reporter/app.py` — the reading UI and signal capture (first ~350 lines)
5. `curation_agent/prompts/*.txt` — the three prompts are short and reveal the intent of every LLM call
