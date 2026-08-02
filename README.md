# Anupam Sarkar — Agentic Portfolio

An AI-agent portfolio. The homepage is a conversational agent: a landing screen
with a breathing orb and topic chips, and a chat workspace where the agent
"thinks" through a visible state rail, then answers with rich cards — case
files, framework cards, an about timeline, and follow-up chips. Free-text
questions are routed by intent to the right answer.

Built as a fully static site: no build step, no dependencies, plain HTML/CSS/JS.

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
- **Free text** is routed by keyword to topics or cases; everything else hits a
  small local knowledge base (hardest decision, impact numbers, leadership,
  career arc, education, location…), with a graceful fallback.
- **Password gate** — each entry in `CASE_LINKS` (top of the script in
  `index.html`) takes a `url` and optional `pw`; set a password to gate a case
  study behind the modal. All are open by default.
- To make free text a **live LLM agent**, point `askAgent()` at a small backend
  endpoint that proxies the Anthropic API with your key (never ship an API key
  client-side).

## Run locally

Any static file server works:

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

Or simply open `index.html` in a browser.

## Deploy with GitHub Pages

1. Merge this branch into the default branch.
2. In the repository, go to **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to *Deploy from a branch*,
   pick the default branch and the `/ (root)` folder, then **Save**.
4. The site goes live at `https://<username>.github.io/New-portfolio/` within a
   couple of minutes.

The `.nojekyll` file is included so GitHub Pages serves the files as-is.
