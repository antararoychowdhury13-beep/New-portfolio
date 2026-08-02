# Anupam Sarkar — Interactive Portfolio

An intent-first portfolio website. Instead of browsing, visitors ask the on-page
agent console a question ("prove leadership", "show measurable impact") and it
resolves to real evidence — metrics, decisions, and case studies.

Built as a fully static site: no build step, no dependencies, plain HTML/CSS/JS.

## Pages

| Page | What it is |
|---|---|
| `index.html` | The agent console, gravity capability field, and indexed work grid |
| `career-journey.html` | The 12-year arc, Faraka → IBM |
| `case-smart-mining.html` | Siemens · Smart Mining case file |
| `case-nextwork.html` | Siemens · #NextWork case file |
| `case-khetmitra.html` | John Deere India · KhetMitra case file |
| `case-incident-bart.html` | Microsoft Teams · BART case file |
| `case-deere-pioneers.html` | John Deere · Farm Pioneers case file |

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
