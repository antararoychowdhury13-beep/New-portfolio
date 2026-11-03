/**
 * Perception layer — turns an uploaded screenshot into a structured inventory
 * of what is actually on the screen.
 *
 * This is the foundation the rest of the engine stands on. Everything
 * downstream (persona behaviour, task generation, hazard scoring) is supposed
 * to consume THIS and nothing else — no DOM, no filenames, no author-supplied
 * labels. That restriction is the "perception firewall": a synthetic
 * participant must only know what a human could see at a glance.
 *
 * Runs on Cloudflare Workers AI, so it needs no API key — only the `AI`
 * binding in wrangler.jsonc. The free allocation is per-account per-day, so
 * the expensive call happens ONCE PER SCREEN and is cached by image hash.
 * Twelve simulated participants all read the same cached inventory.
 */

export const SCHEMA = "synthux.screen-inventory/1";

/**
 * Candidate models. `kind` selects the request shape:
 *   moondream — dedicated image-to-text task API ({task, image, question})
 *   chat      — multimodal chat completion (OpenAI-style content parts)
 */
export const VISION_MODELS = {
  moondream: { id: "@cf/moondream/moondream3.1-9B-A2B", kind: "moondream" },
  qwen: { id: "@cf/qwen/qwen3.8-27b", kind: "chat" },
  llama: { id: "@cf/meta/llama-3.2-11b-vision-instruct", kind: "chat" },
  mistral: { id: "@cf/mistralai/mistral-small-3.1-24b-instruct", kind: "chat" },
};

export const DEFAULT_MODEL = "qwen";

const INVENTORY_PROMPT = `You are a perception system for usability testing. Look at this screenshot of a software interface and report ONLY what is visually present. Never guess what happens after a click, never infer hidden content, never invent labels you cannot read.

Return STRICT JSON, no prose, no markdown fence, matching exactly:

{
  "screen_purpose": "<one short sentence: what this screen is for>",
  "primary_action": "<the visible label of the single most prominent action, or null>",
  "elements": [
    {
      "label": "<the exact visible text, verbatim; \\"\\" if it is a pure icon>",
      "role": "button|link|tab|input|text|heading|metric|table|image|icon|other",
      "prominence": "primary|secondary|tertiary",
      "interactive": true|false,
      "region": "header|nav|main|sidebar|footer"
    }
  ],
  "headings": ["<every heading or title you can read, verbatim>"],
  "reading_order": ["<element labels in the order the eye would meet them>"],
  "observations": ["<only visually checkable facts: faint or low-contrast text, very small tap targets, crowding, truncation, unlabelled icons>"]
}

Rules:
- Transcribe text EXACTLY as shown, including currency symbols and numbers.
- List at most 40 elements; when a table repeats rows, describe the table once.
- "prominence" is about visual weight (size, colour, contrast, position) only.
- If you cannot read something, leave it out rather than guessing.
- Output the JSON object and nothing else.`;

/** FNV-1a over the base64 payload — stable cache key, no crypto needed. */
export function imageHash(b64) {
  let h = 0x811c9dc5;
  for (let i = 0; i < b64.length; i++) {
    h ^= b64.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0") + ":" + b64.length;
}

/** Pull a JSON object out of a model reply that may be fenced or chatty. */
export function parseLooseJSON(text) {
  if (typeof text !== "string") return null;
  let s = text.trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1].trim();
  const start = s.indexOf("{");
  if (start === -1) return null;
  // walk to the matching brace so trailing commentary is ignored
  let depth = 0,
    inStr = false,
    esc = false;
  for (let i = start; i < s.length; i++) {
    const c = s[i];
    if (esc) {
      esc = false;
      continue;
    }
    if (c === "\\") {
      esc = true;
      continue;
    }
    if (c === '"') inStr = !inStr;
    if (inStr) continue;
    if (c === "{") depth++;
    else if (c === "}" && --depth === 0) {
      try {
        return JSON.parse(s.slice(start, i + 1));
      } catch {
        return null;
      }
    }
  }
  return null;
}

/** Normalise whatever the model returned into the documented schema. */
export function normaliseInventory(raw) {
  const ROLES = ["button", "link", "tab", "input", "text", "heading", "metric", "table", "image", "icon", "other"];
  const PROM = ["primary", "secondary", "tertiary"];
  const REGIONS = ["header", "nav", "main", "sidebar", "footer"];
  const str = (v, max = 200) => (typeof v === "string" ? v.trim().slice(0, max) : "");
  const arr = (v) => (Array.isArray(v) ? v : []);

  const elements = arr(raw?.elements)
    .slice(0, 40)
    .map((e) => ({
      label: str(e?.label),
      role: ROLES.includes(e?.role) ? e.role : "other",
      prominence: PROM.includes(e?.prominence) ? e.prominence : "tertiary",
      interactive: e?.interactive === true,
      region: REGIONS.includes(e?.region) ? e.region : "main",
    }))
    .filter((e) => e.label || e.role === "icon");

  return {
    schema: SCHEMA,
    screen_purpose: str(raw?.screen_purpose, 300),
    primary_action: str(raw?.primary_action) || null,
    elements,
    headings: arr(raw?.headings).map((h) => str(h)).filter(Boolean).slice(0, 20),
    reading_order: arr(raw?.reading_order).map((h) => str(h)).filter(Boolean).slice(0, 40),
    observations: arr(raw?.observations).map((h) => str(h, 300)).filter(Boolean).slice(0, 20),
  };
}

/** True when the inventory carries enough signal to drive a simulation. */
export function inventoryIsUsable(inv) {
  return !!inv && inv.elements.length >= 3 && (!!inv.screen_purpose || inv.headings.length > 0);
}

/* ------------------------------------------------------------------ */
/* model invocation                                                    */
/* ------------------------------------------------------------------ */

function dataUri(b64, mime) {
  return b64.startsWith("data:") ? b64 : `data:${mime || "image/png"};base64,${b64}`;
}

function bareBase64(b64) {
  const m = b64.match(/^data:[^;]+;base64,(.*)$/s);
  return m ? m[1] : b64;
}

/** Request shapes to try, in order, for a multimodal chat model. */
function chatShapes(b64, mime, prompt) {
  const uri = dataUri(b64, mime);
  return [
    {
      name: "openai-content-parts",
      body: {
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: prompt },
              { type: "image_url", image_url: { url: uri } },
            ],
          },
        ],
        max_tokens: 2048,
        temperature: 0.1,
      },
    },
    {
      name: "image_url-string",
      body: {
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: prompt },
              { type: "image_url", image_url: uri },
            ],
          },
        ],
        max_tokens: 2048,
        temperature: 0.1,
      },
    },
    {
      name: "prompt-plus-bytes",
      body: {
        prompt,
        image: Array.from(
          Uint8Array.from(atob(bareBase64(b64)), (c) => c.charCodeAt(0))
        ),
        max_tokens: 2048,
      },
    },
  ];
}

function textOf(result) {
  if (typeof result === "string") return result;
  return (
    result?.response ??
    result?.result?.response ??
    result?.choices?.[0]?.message?.content ??
    result?.description ??
    result?.text ??
    ""
  );
}

/**
 * Call one vision model, trying each request shape until one is accepted.
 * Returns { text, shape, model, attempts } or throws with every attempt's error.
 */
export async function callVisionModel(env, modelKey, b64, mime, prompt) {
  const spec = VISION_MODELS[modelKey];
  if (!spec) throw new Error(`unknown model "${modelKey}"`);
  if (!env.AI) throw new Error("Workers AI binding `AI` is not configured on this Worker");

  const shapes =
    spec.kind === "moondream"
      ? [
          {
            name: "moondream-query",
            body: {
              task: "query",
              image: dataUri(b64, mime),
              question: prompt,
              reasoning: false,
              temperature: 0.1,
              max_tokens: 2048,
            },
          },
        ]
      : chatShapes(b64, mime, prompt);

  const attempts = [];
  for (const shape of shapes) {
    const t0 = Date.now();
    try {
      const result = await env.AI.run(spec.id, shape.body);
      const text = textOf(result);
      if (!text) throw new Error("empty response");
      attempts.push({ shape: shape.name, ok: true, ms: Date.now() - t0 });
      return {
        text,
        shape: shape.name,
        model: spec.id,
        ms: Date.now() - t0,
        usage: result?.usage ?? null,
        attempts,
      };
    } catch (e) {
      attempts.push({
        shape: shape.name,
        ok: false,
        ms: Date.now() - t0,
        error: String(e?.message || e).slice(0, 300),
      });
    }
  }
  const err = new Error(`all request shapes failed for ${spec.id}`);
  err.attempts = attempts;
  throw err;
}

/* ------------------------------------------------------------------ */
/* cached entry point                                                  */
/* ------------------------------------------------------------------ */

/**
 * Perceive one screen. Cached by (image hash, model, schema) in the Workers
 * Cache API, so re-running a study costs nothing and twelve participants
 * reading the same screen cost one call.
 */
export async function perceiveScreen(env, ctx, { image, mime, model = DEFAULT_MODEL, noCache = false }) {
  const b64 = bareBase64(image);
  const hash = imageHash(b64);
  const cacheUrl = `https://perception.local/${encodeURIComponent(SCHEMA)}/${model}/${encodeURIComponent(hash)}`;
  const cache = caches.default;

  if (!noCache) {
    const hit = await cache.match(new Request(cacheUrl));
    if (hit) {
      const body = await hit.json();
      return { ...body, provenance: { ...body.provenance, cached: true } };
    }
  }

  const t0 = Date.now();
  const call = await callVisionModel(env, model, image, mime, INVENTORY_PROMPT);
  const parsed = parseLooseJSON(call.text);
  const inventory = normaliseInventory(parsed || {});

  const payload = {
    schema: SCHEMA,
    image_hash: hash,
    inventory,
    provenance: {
      status: inventoryIsUsable(inventory) ? "live" : "degraded",
      reason: inventoryIsUsable(inventory)
        ? "screen read by a vision model on Cloudflare Workers AI"
        : parsed
        ? "the model replied but the inventory was too thin to drive a simulation"
        : "the model reply could not be parsed as the inventory schema",
      pixels_read: true,
      provider: "cloudflare-workers-ai",
      model: call.model,
      request_shape: call.shape,
      elements_found: inventory.elements.length,
      ms: Date.now() - t0,
      usage: call.usage,
      cached: false,
    },
  };

  if (!noCache && payload.provenance.status === "live") {
    const res = new Response(JSON.stringify(payload), {
      headers: { "content-type": "application/json", "cache-control": "max-age=2592000" },
    });
    const put = cache.put(new Request(cacheUrl), res);
    if (ctx?.waitUntil) ctx.waitUntil(put);
    else await put;
  }
  return payload;
}

/* ------------------------------------------------------------------ */
/* flow graph                                                          */
/* ------------------------------------------------------------------ */

const STOP = new Set(["the", "a", "an", "to", "of", "and", "or", "for", "your", "my", "all", "new", "view", "page", "screen"]);

function tokens(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 2 && !STOP.has(t));
}

function overlap(a, b) {
  const A = new Set(tokens(a));
  if (!A.size) return 0;
  const B = tokens(b);
  if (!B.length) return 0;
  let hit = 0;
  for (const t of new Set(B)) if (A.has(t)) hit++;
  return hit / Math.max(A.size, new Set(B).size);
}

/**
 * Link perceived screens into a navigable graph.
 *
 * An edge means: this interactive element on screen i plausibly leads to
 * screen j, because the element's visible label matches that screen's purpose
 * or a heading on it. Edges are evidence-bearing — each carries the label it
 * was derived from and a confidence — so a wrong turn in the simulation can
 * be traced back to something a human could actually have read.
 */
export function buildFlowGraph(screens) {
  const nodes = screens.map((s, i) => ({
    index: i,
    label: s.label || `Screen ${i + 1}`,
    purpose: s.inventory?.screen_purpose || "",
    headings: s.inventory?.headings || [],
    primary_action: s.inventory?.primary_action || null,
    element_count: s.inventory?.elements?.length || 0,
  }));

  const edges = [];
  screens.forEach((from, i) => {
    const interactive = (from.inventory?.elements || []).filter((e) => e.interactive && e.label);
    interactive.forEach((el) => {
      let best = null;
      screens.forEach((to, j) => {
        if (i === j) return;
        const target = [to.inventory?.screen_purpose, ...(to.inventory?.headings || [])].join(" ");
        const score = overlap(el.label, target);
        if (score > 0.3 && (!best || score > best.confidence)) {
          best = { from: i, to: j, via: el.label, prominence: el.prominence, confidence: +score.toFixed(2) };
        }
      });
      if (best) edges.push(best);
    });
    // a step forward in the uploaded sequence is itself weak evidence
    if (i + 1 < screens.length && !edges.some((e) => e.from === i && e.to === i + 1)) {
      edges.push({ from: i, to: i + 1, via: from.inventory?.primary_action || null, prominence: "primary", confidence: 0.25, inferred: "sequence" });
    }
  });

  const reachable = new Set([0]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const e of edges) if (reachable.has(e.from) && !reachable.has(e.to)) (reachable.add(e.to), (grew = true));
  }

  return {
    schema: "synthux.flow-graph/1",
    nodes,
    edges,
    orphans: nodes.filter((n) => !reachable.has(n.index)).map((n) => n.index),
    // how much of the graph rests on real labels rather than upload order
    label_derived_edges: edges.filter((e) => !e.inferred).length,
  };
}
