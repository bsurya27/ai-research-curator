# AI Research Curator

A two-agent personalized AI research curation system that learns your interests over time and delivers a daily briefing of the most relevant content from across the web.

## How It Works

**Agent 1 — Curator (runs daily on AWS EC2)**

- Reads preference signals from storage (S3 when `STORAGE_BACKEND=s3`, or local files under `curation_agent/data/`) written by the reporter
- Updates a preference vector in embedding space based on your engagement (via the rec model API)
- Runs KMeans on all stored embeddings (up to **6** clusters); uses the **3** clusters closest to your preference vector to drive query generation
- Uses Claude to generate targeted search queries from those clusters (cold-start path uses onboarding keywords when the vector store has fewer than 50 items)
- Scrapes ArXiv, Reddit, Twitter (Apify-backed), and Dev.to for fresh content
- Embeds and scores new items against your preference vector
- Generates a personalized markdown briefing using Claude
- Writes briefing, signals clearing, weights, etc. back to S3 or local paths; optionally uploads the run log to S3 when using S3 storage

**Agent 2 — Reporter (always-on on HF Spaces)**

- Reads today's briefing from S3 or local `curation_agent/data/briefing.md`
- Displays it as a card-based Streamlit UI
- Lets you rate items (1–5 stars), mark read, and chat about the content
- Extracts preference signals from your interactions
- Writes signals back to storage for the curator to consume on the next run

**Recommendation Model (FastAPI service)**

- Embedding via OpenAI `text-embedding-3-small`
- Vector store via ChromaDB
- Preference vector — unit vector in 1536-dim embedding space, updated via implicit feedback from the `/update` endpoint
- KMeans (`n_clusters=6` on the full corpus; **k=3** nearest clusters returned for daily curation) to discover topic regions
- Cosine similarity scoring

## Architecture

```
Daily: EC2 Curator → scrape → embed → score → generate briefing → S3 (or local)
User:  Reporter (HF) → ratings + chat → extract signals → S3 
Next:  Curator reads signals → update preference vector → new scraping queries
```

## Project Structure

```
ai-research-curator/
├── scraping/               # Source scrapers (ArXiv, Apify Reddit/Twitter, Dev.to)
├── rec_model/              # Recommendation model + FastAPI endpoints
│   ├── embedder.py         # OpenAI text-embedding-3-small
│   ├── vector_store.py     # ChromaDB wrapper
│   ├── preference.py       # Preference vector management
│   ├── cluster.py          # KMeans clustering
│   ├── scorer.py           # Cosine similarity scoring
│   └── app.py              # FastAPI service
├── curation_agent/         # Agent 1 — daily EC2 runner
│   ├── curator.py          # Main orchestration loop
│   ├── tools.py            # Scraping + rec model API wrappers
│   ├── logger.py           # Structured JSON logging
│   └── prompts/            # LLM prompts for query gen + briefing
├── reporter/               # Agent 2 — HF Spaces UI
│   ├── app.py              # Streamlit app
│   └── prompts/            # Signal extraction prompt
├── onboarding/             # Cold start keyword selection UI
│   └── app.py
└── experiments/            # Embedding model experiments + data collection
```

## Setup

### Prerequisites

- Python 3.11+
- OpenAI API key
- Anthropic API key
- Apify API token (Reddit + Twitter actors used by active scrapers)
- Reddit app credentials (see `.env.example`) as needed for your setup
- AWS account (S3, EC2) if you deploy with cloud storage and a scheduled curator

### Environment Variables

Copy `.env.example` to `.env` and fill in values. Commonly:

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
APIFY_API_TOKEN=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=
# Twitter / Apify-related vars as in .env.example (e.g. TWITTER_AUTH_TOKEN, TWITTER_CT0)
STORAGE_BACKEND=s3   # or omit / use "local" for filesystem under repo paths
S3_BUCKET=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=
CHROMA_PERSIST_DIR=
PREFERENCE_PATH=
```

### Local Development

1. Clone the repo
2. Create `.env` with your keys (start from `.env.example`)
3. Install dependencies: `pip install -r requirements.txt` (optional: use a venv, e.g. `python -m venv curator` and activate it)
4. Run onboarding (optional cold start): `streamlit run onboarding/app.py` (from repo root)
5. Start rec model: `cd rec_model && python app.py` (serves FastAPI on port 8000 with uvicorn)
6. Run curator: `cd curation_agent && python curator.py`
7. Run reporter: `cd reporter && streamlit run app.py`

Ensure `curation_agent/tools.py` `REC_MODEL_URL` matches where the rec model is running (default `http://localhost:8000`).

### Production Deployment

- **Curator**: AWS EC2 (e.g. t3.micro), triggered daily (e.g. EventBridge → SSM/SSM-less cron)
- **Reporter**: Hugging Face Spaces (Streamlit)
- **Shared state**: AWS S3 when `STORAGE_BACKEND=s3` (otherwise local paths aligned with `PREFERENCE_PATH` / `rec_model` data dirs)

SNS “briefing ready” hooks are stubbed in code (`reporter/app.py`); wire them if you want push notifications.

## Key Design Decisions

- **Unsupervised clustering** — topic regions emerge from content geometry; no hardcoded categories
- **Preference vector** — single unit vector in embedding space, updated from like/dislike signals via the rec model
- **Deterministic agent flow** — LLM calls mainly at query generation and briefing writing (plus cold-start query path)
- **Source weights** — per-source engagement adjusts scraping emphasis over time (`source_weights.json` beside preference storage)
- **Cold start** — onboarding keywords seed the preference vector and cold-start queries when `item_count < 50`

---
