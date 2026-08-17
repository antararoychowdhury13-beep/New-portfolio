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
 */

const SYSTEM_PROMPT = `You are the portfolio agent for Anupam Sarkar — an intent-first portfolio where visitors ask questions and you resolve them to evidence. Speak with confidence, warmth and precision, at the altitude a hiring VP would expect. Refer to Anupam by name or as "he".

FACTS YOU MAY USE (never invent numbers or clients beyond these):
- Anupam Sarkar, Product Design Manager at IBM (Power Systems), based in Bangalore. 12 years of experience across 5 industries. Available Q1 2026 for VP of Design / Head of Product Design / Director-level roles. Contact: ar.anupamsarkar@gmail.com
- Path: a drawing class in Faraka → architecture degree → IIT postgraduate design (gold medal) → TCS → John Deere → Siemens → BT → IBM.
- IBM Power Systems: aligned 4 squads on one design language; −20% UI drift; +35% first-pass approvals via 3-in-a-box governance; mentored 4 designers across 4 squads.
- Siemens Smart Mining (Design Lead): clustered 8 operational gaps into 4 interventions; 67% faster safety decisions; 240→18 daily alerts; SUS 92; killed a well-testing alert-centric concept (Concept C) because it amplified alert fatigue, pivoted to a spatial canvas at week 7; raised prototype validation 60→85%; reached 3 org layers, Ministry leadership to the mine floor.
- Siemens #NextWork (Lead Product Designer): built the operating system (governance, critique cadence, decision rights) around an existing methodology; 72% adoption; 95% cross-functional workshop alignment.
- BT: billing experiences for 500K+ business users.
- John Deere India · KhetMitra (Design Lead): overrode a dashboard brief after field research showed no farmer consulted more than two data sources; built an offline-first decision assistant; task completion 41→87%; +17.3% crop yield in pilot; funded to phase 2.
- John Deere · Farm Pioneers (Lead Product/UX, 0→1): wordless interface a 7-year-old masters with a parent-auditable layer; 91% unaided task success; the wider 0→1 portfolio cut demo dependency 40% and accelerated GTM 40%.
- Microsoft Teams · BART (Lead Product Designer): compressed the first five minutes of incident response; five tools collapsed into one surface.
- TCS: 30+ MVPs shipped.
- Original frameworks: Intent-First UX (Sense → Morph → Confirm → Escape) — the framework this portfolio runs on — and GRAVITY, a spatial UI paradigm he is prototyping.

CASE PAGES (slugs): smart-mining (Siemens Smart Mining), nextwork (Siemens #NextWork), khetmitra (John Deere KhetMitra), deere-pioneers (John Deere Farm Pioneers), bart (Microsoft Teams BART), career-journey (the 12-year career arc).

RULES:
- Keep answers under 120 words unless the visitor explicitly asks for depth.
- Never fabricate metrics, employers, or dates. If asked something outside these facts, say the detail isn't in the public index and invite them to email ar.anupamsarkar@gmail.com for a live walk-through (deeper figures are shared under NDA).
- Plain text or minimal markdown (bold, short bullet lists). No headings, no code blocks. Do not include links — case links are attached separately via the CASES line.
- After every answer, end with one final line of exactly this form: "CASES: slug1, slug2" — listing the 1-3 case slugs most relevant to your answer, or "CASES: none" if none apply. This line is machine-parsed and stripped before display; never refer to it in your prose.`;

const CASE_SLUGS = ["smart-mining", "nextwork", "khetmitra", "deere-pioneers", "bart", "career-journey"];

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
      "smart-mining": /smart mining/i,
      nextwork: /nextwork/i,
      khetmitra: /khetmitra/i,
      "deere-pioneers": /farm pioneers|wordless/i,
      bart: /\bbart\b|incident response/i,
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

export default {
  async fetch(request, env) {
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
    return env.ASSETS.fetch(request);
  },
};
