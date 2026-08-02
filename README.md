# Anupam Sarkar — Agentic Portfolio

An AI-agent portfolio. The homepage is a conversational agent: a landing screen
with a breathing orb and topic chips, and a chat workspace where the agent
"thinks" through a visible state rail, then answers with rich cards — case
files, framework cards, an about timeline, and follow-up chips. Free-text
questions are routed by intent to the right answer.

The site itself is plain HTML/CSS/JS with no build step. Free-text questions
are answered by a **live AI agent** — a small Cloudflare Worker
(`worker.js`) that calls the Anthropic API with a server-side key — with a
built-in local knowledge base as the offline fallback.

## Pages

| Page | What it is |
|---|---|
| `index.html` | The agent — landing (orb + chips + ask bar) and chat workspace (sidebar, thread, state rail, cards) |
| `console.html` | The previous intent-first console homepage, kept as an archive |
| `career-journey.html` | The 12-year arc, Faraka → IBM |
| `case-smart-mining.html` | Siemens · Smart Mining case file |
| `case-nextwork.html` | Siemens · #NextWork case file |
| `case-khetmitra.html` | John Deere India · KhetMitra case file |
| `case-incident-bart.html` | Microsoft Teams · BART case file |
| `case-deere-pioneers.html` | John Deere · Farm Pioneers case file |

## How the agent works

- **Topic chips / sidebar nav** open scripted answers (About, Work, Frameworks,
  0→1 Projects, Connect) rendered as rich cards in the chat thread.
- **Project cards** expand into in-thread case-study cards (challenge, role,
  what I did, impact) with a link to the full case file page.
- **Free text** is routed by keyword to topics or cases; everything else goes
  to the **live AI agent** (`POST /api/agent`, served by `worker.js`). If the
  backend is missing or unconfigured, the page falls back to a small local
  knowledge base (hardest decision, impact numbers, leadership, career arc,
  education, location…), then to a graceful "try one of these" answer.
- **Password gate** — each entry in `CASE_LINKS` (top of the script in
  `index.html`) takes a `url` and optional `pw`; set a password to gate a case
  study behind the modal. All are open by default.

## The live AI agent (Cloudflare Worker)

`worker.js` serves the static site and exposes `POST /api/agent`. It calls the
Anthropic API (`claude-opus-5`) with a system prompt containing Anupam's
portfolio facts — the same content as the case files, so answers stay
grounded. The API key lives in a Worker secret and never reaches the browser.
The endpoint only accepts same-origin requests, caps history at 10 turns /
2,000 chars per message, and prompt-caches the system prompt to keep costs
down.

Deploy:

```bash
npm install
npx wrangler login
npx wrangler secret put ANTHROPIC_API_KEY   # paste your key (console.anthropic.com)
npx wrangler deploy
```

Without the secret, `/api/agent` returns 503 and the site quietly uses the
local knowledge base instead — so the same code also works as a plain static
site. To change the model or the agent's persona/facts, edit `AGENT_SYSTEM`
and the `model` field in `worker.js`.

## Run locally

Any static file server works:

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

Or simply open `index.html` in a browser.

## Deploy with GitHub Pages (static only)

1. Merge this branch into the default branch.
2. In the repository, go to **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to *Deploy from a branch*,
   pick the default branch and the `/ (root)` folder, then **Save**.
4. The site goes live at `https://<username>.github.io/New-portfolio/` within a
   couple of minutes.

The `.nojekyll` file is included so GitHub Pages serves the files as-is.
GitHub Pages can't run the Worker, so free-text answers use the local
knowledge base there; deploy to Cloudflare (above) for the live agent.
