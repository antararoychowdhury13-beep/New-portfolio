/**
 * Portfolio chatbot API — serves /api/chat, everything else falls through
 * to the static assets.
 *
 * Provider chain: OpenAI gpt-4o-mini (primary) → Ollama (secondary).
 * The frontend keeps its keyword-routed canned answers as a final offline
 * fallback when this endpoint returns an error.
 *
 * Configuration (Worker settings → Variables and Secrets):
 *   OPENAI_API_KEY   secret — required for the primary provider
 *   OPENAI_MODEL     var    — optional, defaults to "gpt-4o-mini"
 *   OLLAMA_BASE_URL  var    — optional, e.g. "https://ollama.example.com:11434"
 *   OLLAMA_MODEL     var    — optional, defaults to "llama3.2"
 *   OLLAMA_API_KEY   secret — optional, sent as a Bearer token if set
 *
 * Also serves the Testing Lab's perception layer on /api/vision, /api/flow
 * and /api/vision/selftest. Those run on the Workers AI `AI` binding and need
 * no key or secret at all.
 */

import {
  SCHEMA,
  VISION_MODELS,
  DEFAULT_MODEL,
  perceiveScreen,
  buildFlowGraph,
} from "./vision.js";

const SYSTEM_PROMPT = `You are the portfolio agent for Anupam Sarkar — an intent-first portfolio where visitors ask questions and you resolve them to evidence. Speak with confidence, warmth and precision, at the altitude a hiring VP would expect. Refer to Anupam by name or as "he".

FACTS YOU MAY USE (never invent numbers or clients beyond these):
- Anupam Sarkar, Product Design Manager at IBM (Power Systems), based in Bengaluru. 12 years of experience across 5 industries. Contact: ar.anupamsarkar@gmail.com
- Path: a drawing class in Faraka → architecture degree → IIT postgraduate design (gold medal) → TCS → John Deere → Siemens → BT → IBM.
- IBM Power Systems (Product Design Manager): aligned 4 squads on one design language; −20% UI drift; +35% first-pass approvals via 3-in-a-box governance; mentored 4 designers across 4 squads.
- IBM PowerVC (UX Design Lead, H1 2026): evolved a notification experience that treated every system event like another message into an actionable severity system (severity, timing, ownership, next action — badges, panels, expiring certificates, failed SSH connections, service restarts); 72+ screens across five parallel workstreams; feedback rounds grew 2.5× Jan→Jun; hardest trade-off: chose delivery breadth over research depth (one formal discovery session in H1, logged openly as an H2 watch item).
- Siemens Smart Mining (Design Lead; no public case page — use CASES: career-journey if relevant): clustered 8 operational gaps into 4 interventions; 67% faster safety decisions; 240→18 daily alerts; SUS 92; killed a well-testing alert-centric concept (Concept C) because it amplified alert fatigue, pivoted to a spatial canvas at week 7; raised prototype validation 60→85%; reached 3 org layers, Ministry leadership to the mine floor.
- Siemens #NextWork (Lead Product Designer): built the operating system (governance, critique cadence, decision rights) around an existing methodology; 72% adoption; 95% cross-functional workshop alignment.
- BT Business · Billing (Lead Product Designer): an evidence-first redesign of the billing service for 340,000 business customers (£155M+ monthly payments), diagnosed entirely from the public record — 120K+ Trustpilot reviews, 8,400 Resolver disputes and 600+ forum threads coded into one root cause (no single source of truth); aligned 5 functions; 6 design principles; targets benchmarked to competitors (portal completion 12%→78%). An independent diagnostic.
- John Deere India · KhetMitra (Design Lead): overrode a dashboard brief after field research showed no farmer consulted more than two data sources; built an offline-first decision assistant; task completion 41→87%; +17.3% crop yield in pilot; funded to phase 2.
- John Deere · Farm Pioneers (Lead Product/UX, 0→1): wordless interface a 7-year-old masters with a parent-auditable layer; 91% unaided task success; the wider 0→1 portfolio cut demo dependency 40% and accelerated GTM 40%.
- Microsoft Teams · BART (Lead Product Designer): compressed the first five minutes of incident response; five tools collapsed into one surface.
- TCS: 30+ MVPs shipped.
- Original frameworks: Intent-First UX (Sense → Morph → Confirm → Escape) — the framework this portfolio runs on — and GRAVITY, a spatial UI paradigm he is prototyping.
- Bootstrap founder: built and launched DFD (Digital First Devotional), a live devotional app with a Panchang recommendation engine (six-layer scoring), mala counter, streaks and an admin/content system.

AI WORK (hands-on; he designs AND builds with AI — say plainly which items are live, code, or concept):
- UX KPI Testing Lab (LIVE on this site): synthetic usability testing. Upload before/after screens, generate a persona panel, and every persona expands into simulated participants; task success, confidence intervals and friction severity are measured from those sessions rather than guessed by one prompt, so before/after deltas are attributable to the design change. Reports are explicitly framed as predictions to verify with real users.
- Buddy (LIVE demo on this site; code public): a proactive AI assistant. A trust engine scores every candidate insight for confidence and tiers it silent / passive / ambient / proactive, so only what clears the bar interrupts you; confirm/dismiss feedback retunes trust per life domain; Claude composes the daily briefing; on-device voice (Whisper speech-to-text, Kokoro text-to-speech); remembers personal facts via tool-calling.
- Saanjh (design concept): a voice agent for elderly care. One agent, one voice, one conversation, read four ways (surface, wellbeing, clinical, risk) instead of four separate modes; a six-grade escalation ladder (L0 note → L5 emergency) where she is told before anyone else is at every level except a life-threatening emergency; families never get transcripts, only a short lossy weekly summary; turn-taking tuned to 2.5–3s silence tolerance for older speakers; the agent never claims to feel emotions.
- This portfolio agent: text answers via gpt-4o-mini with an Ollama fallback and an offline keyword index, plus a live voice call via ElevenLabs.
- AI-native workflow: Figma-to-code bidirectional workflow using MCP with Claude Code; Parity, a zero-defect design handoff system (handoff contract editor + validation console) for IBM HMC design QA; Figma plugins (Carbon Content Recommender, Design Spec Exporter); a library of custom AI skills for research synthesis, case-study narrative, data visualisation and diagrams; multi-agent research pipelines. These are shown in live walk-throughs, not publicly.
- Scheduled AI workflows (running every weekday at 07:00 IST since Aug 2026): a Daily AI Updates card report (web research on the last 24–72h, 8–12 sourced items, designed card page, email + phone summary; says honestly when a day is quiet) and an AI Scout brief for designers in India (5 sections of 10–20 items; every item must have a real working source link or it is dropped; the agent renders the page in a real browser and checks the screenshot before delivering). Pattern he'd bring to a team: scheduled trigger → research → verification gate → designed output → honest "nothing today".
- On-demand AI pipelines (7): AI research partner; synthetic usability testing; a case-study pipeline of five specialist skills (narrative architect → template builder → narrative writer → data visualiser → diagram architect, with him choosing the story and approving the edit); Figma ↔ code through MCP; Parity handoff QA; a nine-stage course pipeline (offer → audience research → backward-designed curriculum → lessons → diagrams → posts → sales prep → post-cohort revision); and the portfolio agent's fallback chain. Every workflow follows one pattern: trigger → gather → verify → design → check → deliver, with humans at the judgement steps. Sample outputs of both scheduled workflows are on the workflows page.
- Design operations: ran PowerVC's five parallel workstreams from one tracker on a monthly audit rhythm; 3-in-a-box governance and critique cadence on Power Systems (+35% first-pass approvals); Parity handoff contracts; a UX complexity scoring tool based on IBM's Sobiesiak/O'Keefe method.
- AI for research: a reusable AI UX researcher that first questions the research question (what decision it informs, what would change our mind), covers the full 7-stage lifecycle, keeps evidence separate from insight, tags every finding with confidence, and refuses to overclaim small samples; plus a researcher agent pipeline, a video annotation tool and GazeLab webcam eye-tracking. He deliberately hand-coded the BT Billing complaint synthesis because that synthesis was the whole argument.
- Teaching: building a course that teaches designers an AI-native workflow across the whole product lifecycle.
- Point of view: synthetic users predict, they don't replace real research; an AI agent should never claim feelings it doesn't have; never invent numbers; consent before disclosure.

CASE PAGES (slugs): ai-work (overview of all his AI work), workflows (every scheduled and on-demand AI workflow, stage by stage, with sample outputs), uxkpi-lab (live synthetic usability testing lab), buddy (live Buddy demo), ibm-power (IBM Power Systems), smart-mining (IBM PowerVC — the slug name is historical; it is NOT Siemens Smart Mining), nextwork (Siemens #NextWork), khetmitra (John Deere KhetMitra), deere-pioneers (John Deere Farm Pioneers), bart (Microsoft Teams BART), bt-billing (BT Business Billing service redesign), career-journey (the 12-year career arc).

RULES:
- Keep answers under 120 words unless the visitor explicitly asks for depth.
- Never fabricate metrics, employers, or dates. If asked something outside these facts, say the detail isn't in the public index and invite them to email ar.anupamsarkar@gmail.com for a live walk-through (deeper figures are shared under NDA).
- Plain text or minimal markdown (bold, short bullet lists). No headings, no code blocks. Do not include links — case links are attached separately via the CASES line.
- After every answer, end with one final line of exactly this form: "CASES: slug1, slug2" — listing the 1-3 case slugs most relevant to your answer, or "CASES: none" if none apply. This line is machine-parsed and stripped before display; never refer to it in your prose.`;

const CASE_SLUGS = ["workflows", "ai-work", "uxkpi-lab", "buddy", "ibm-power", "smart-mining", "nextwork", "khetmitra", "deere-pioneers", "bart", "bt-billing", "career-journey"];

/** Split a model reply into display text and referenced case slugs. */
function extractCases(text) {
  let answer = text;
  let cases = [];
  const m = text.match(/\n?\s*CASES:\s*(.*)\s*$/i);
  if (m) {
    answer = text.slice(0, m.index).trim();
    cases = m[1]
      .split(/[,\s]+/)
      .map((s) => s.trim().toLowerCase())
      .filter((s) => CASE_SLUGS.includes(s));
  }
  if (!cases.length) {
    // fallback: infer from mentions in the answer itself
    const probes = {
      workflows: /workflow|scheduled|pipeline|automat/i,
      "ai-work": /\bAI\b|agent|synthetic|Saanjh/,
      "uxkpi-lab": /testing lab|synthetic (users|usability|personas)/i,
      buddy: /\bbuddy\b/i,
      "ibm-power": /power systems|four squads|4 squads/i,
      "smart-mining": /powervc/i,
      nextwork: /nextwork/i,
      khetmitra: /khetmitra/i,
      "deere-pioneers": /farm pioneers|wordless/i,
      bart: /\bbart\b|incident response/i,
      "bt-billing": /\bbt\b|billing|trustpilot/i,
      "career-journey": /12[- ]year|career (arc|journey|path)|faraka/i,
    };
    cases = CASE_SLUGS.filter((s) => probes[s].test(answer));
  }
  return { answer, cases: cases.slice(0, 3) };
}

async function callOpenAI(env, messages) {
  if (!env.OPENAI_API_KEY) throw new Error("openai: no API key configured");
  const r = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: env.OPENAI_MODEL || "gpt-4o-mini",
      messages,
      temperature: 0.4,
      max_tokens: 400,
    }),
    signal: AbortSignal.timeout(20000),
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => "");
    throw new Error(`openai: HTTP ${r.status} ${detail.slice(0, 300)}`);
  }
  const d = await r.json();
  const text = d.choices?.[0]?.message?.content?.trim();
  if (!text) throw new Error("openai: empty completion");
  return text;
}

async function callOllama(env, messages) {
  if (!env.OLLAMA_BASE_URL) throw new Error("ollama: no base URL configured");
  const headers = { "content-type": "application/json" };
  if (env.OLLAMA_API_KEY) headers.authorization = `Bearer ${env.OLLAMA_API_KEY}`;
  const r = await fetch(env.OLLAMA_BASE_URL.replace(/\/+$/, "") + "/api/chat", {
    method: "POST",
    headers,
    body: JSON.stringify({
      model: env.OLLAMA_MODEL || "llama3.2",
      messages,
      stream: false,
    }),
    signal: AbortSignal.timeout(25000),
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => "");
    throw new Error(`ollama: HTTP ${r.status} ${detail.slice(0, 300)}`);
  }
  const d = await r.json();
  const text = d.message?.content?.trim();
  if (!text) throw new Error("ollama: empty completion");
  return text;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/* ---------------- perception (/api/vision, /api/flow) ---------------- */

/** Base64 payload ceiling — roughly 6 MB of encoded image. */
const MAX_IMAGE_B64 = 8_000_000;

async function handleVision(request, env, ctx) {
  if (request.method !== "POST") return json({ error: "POST only" }, 405);
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }
  const image = typeof body.image === "string" ? body.image : "";
  if (!image) return json({ error: "body.image must be a base64 string or data URI" }, 400);
  if (image.length > MAX_IMAGE_B64)
    return json({ error: `image too large (${image.length} chars, limit ${MAX_IMAGE_B64})` }, 413);

  const model = typeof body.model === "string" && VISION_MODELS[body.model] ? body.model : DEFAULT_MODEL;
  try {
    const out = await perceiveScreen(env, ctx, {
      image,
      mime: typeof body.mime === "string" ? body.mime : "image/png",
      model,
      noCache: body.noCache === true,
    });
    return json(out);
  } catch (e) {
    // A perception failure is reported as a failure. It is never silently
    // swapped for canned output — the caller has to know the numbers that
    // follow were not derived from the pixels.
    return json(
      {
        schema: SCHEMA,
        inventory: null,
        provenance: {
          status: "failed",
          reason: String(e?.message || e).slice(0, 400),
          pixels_read: false,
          provider: "cloudflare-workers-ai",
          model: VISION_MODELS[model]?.id || model,
          attempts: e?.attempts || null,
        },
      },
      502
    );
  }
}

async function handleFlow(request) {
  if (request.method !== "POST") return json({ error: "POST only" }, 405);
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }
  const screens = Array.isArray(body.screens) ? body.screens.slice(0, 40) : null;
  if (!screens?.length) return json({ error: "body.screens must be a non-empty array" }, 400);
  return json(buildFlowGraph(screens));
}

/**
 * Probe every candidate model against a known fixture and report what each
 * one actually read. Used to pick the model and to prove the wiring works;
 * the fixture's ground truth is in public/fixtures/perception-test.png.
 */
async function handleSelftest(request, env, ctx) {
  const url = new URL(request.url);
  const want = url.searchParams.get("model");
  const keys = want && want !== "all" ? want.split(",").filter((k) => VISION_MODELS[k]) : Object.keys(VISION_MODELS);
  if (!keys.length) return json({ error: "no known model selected" }, 400);

  const asset = await env.ASSETS.fetch(new URL("/fixtures/perception-test.png", url.origin));
  if (!asset.ok) return json({ error: "fixture image missing" }, 500);
  const bytes = new Uint8Array(await asset.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  const b64 = btoa(bin);

  const results = {};
  for (const key of keys) {
    const t0 = Date.now();
    try {
      const out = await perceiveScreen(env, ctx, { image: b64, mime: "image/png", model: key, noCache: true });
      results[key] = {
        ok: out.provenance.status === "live",
        status: out.provenance.status,
        model: out.provenance.model,
        shape: out.provenance.request_shape,
        ms: Date.now() - t0,
        usage: out.provenance.usage,
        elements_found: out.provenance.elements_found,
        screen_purpose: out.inventory?.screen_purpose,
        primary_action: out.inventory?.primary_action,
        headings: out.inventory?.headings,
        labels: (out.inventory?.elements || []).map((e) => `${e.role}:${e.label}`),
        observations: out.inventory?.observations,
      };
    } catch (e) {
      results[key] = { ok: false, error: String(e?.message || e).slice(0, 300), attempts: e?.attempts || null, ms: Date.now() - t0 };
    }
  }
  return json({ fixture: "/fixtures/perception-test.png", ai_binding: !!env.AI, results });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/api/chat") {
      if (request.method !== "POST") return json({ error: "POST only" }, 405);
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "invalid JSON body" }, 400);
      }
      const msgs = (Array.isArray(body.messages) ? body.messages : [])
        .filter(
          (m) =>
            m &&
            (m.role === "user" || m.role === "assistant") &&
            typeof m.content === "string" &&
            m.content.trim()
        )
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content.slice(0, 2000) }));
      if (!msgs.length || msgs[msgs.length - 1].role !== "user")
        return json({ error: "messages must end with a user turn" }, 400);

      const messages = [{ role: "system", content: SYSTEM_PROMPT }, ...msgs];
      const errors = [];
      try {
        return json({ ...extractCases(await callOpenAI(env, messages)), provider: "openai" });
      } catch (e) {
        errors.push(String(e.message || e));
      }
      try {
        return json({ ...extractCases(await callOllama(env, messages)), provider: "ollama" });
      } catch (e) {
        errors.push(String(e.message || e));
      }
      return json({ error: "no AI provider available", detail: errors }, 503);
    }
    if (url.pathname === "/api/vision") return handleVision(request, env, ctx);
    if (url.pathname === "/api/vision/selftest") return handleSelftest(request, env, ctx);
    if (url.pathname === "/api/flow") return handleFlow(request);
    return env.ASSETS.fetch(request);
  },
};
