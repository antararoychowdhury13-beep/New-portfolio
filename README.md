# Anupam Sarkar — Interactive Portfolio

An intent-first portfolio website. Instead of browsing, visitors ask the on-page
agent console a question ("prove leadership", "show measurable impact") and it
resolves to real evidence — metrics, decisions, and case studies.

Live at: https://new-portfolio.ar-anupamsarkar.workers.dev/

## Structure

| Path | What it is |
|---|---|
| `public/index.html` | The agent console, gravity capability field, and indexed work grid |
| `public/career-journey.html` | The 12-year arc, Faraka → IBM |
| `public/case-*.html` | Case files: Smart Mining, #NextWork, KhetMitra, BART, Farm Pioneers |
| `public/case.css` | Shared stylesheet for the case pages |
| `src/worker.js` | Cloudflare Worker: serves `/api/chat` (the AI chatbot) + static assets |
| `wrangler.jsonc` | Cloudflare Workers configuration |

## The AI chatbot

Typed questions in the console are answered by a real model through
`POST /api/chat`, with a three-level fallback chain:

1. **OpenAI `gpt-4o-mini`** (primary) — used when `OPENAI_API_KEY` is set
2. **Ollama** (secondary) — used when `OLLAMA_BASE_URL` is set and OpenAI fails
3. **Local keyword index** (offline) — the pre-written evidence answers built
   into the page, used when the API errors out entirely

The quick-prompt chips always use the local index (instant, curated answers).
API keys live only in the Worker — never in the browser.

### Configuration

In the Cloudflare dashboard → Workers & Pages → `new-portfolio` → **Settings →
Variables and Secrets**:

| Name | Type | Required | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | Secret | for primary | OpenAI API key |
| `OPENAI_MODEL` | Variable | no | defaults to `gpt-4o-mini` |
| `OLLAMA_BASE_URL` | Variable | for secondary | e.g. `https://your-host:11434` — must be reachable from Cloudflare, not `localhost` |
| `OLLAMA_MODEL` | Variable | no | defaults to `llama3.2` |
| `OLLAMA_API_KEY` | Secret | no | sent as Bearer token if set |

With neither provider configured the site still works — the console silently
serves the local index.

## Run locally

```bash
npm install -g wrangler
wrangler dev
# open http://localhost:8787
```

To test the chatbot locally against a local Ollama:

```bash
wrangler dev --var OLLAMA_BASE_URL:http://127.0.0.1:11434 --var OLLAMA_MODEL:llama3.2
```

## Deploy

The Cloudflare Workers service `new-portfolio` is connected to this repository;
deploys run `npx wrangler deploy`, which publishes the Worker and uploads
`public/` as static assets. Trigger a deploy from the dashboard (Builds tab) or
run `wrangler deploy` with a Cloudflare API token.
