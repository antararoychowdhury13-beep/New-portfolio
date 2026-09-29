// Screen capture for the Workflows page.
// Drives the live demos in a real browser, captures each step of the UX flow,
// and writes public/shots/*.jpg plus public/shots/manifest.json.
// The Workflows page reads the manifest, so re-running this script refreshes
// every screen and its "captured on" date without touching the HTML.
//
//   npm i playwright && npx playwright install chromium
//   BASE=https://new-portfolio.ar-anupamsarkar.workers.dev node scripts/capture.mjs
//
// Optional: CHROMIUM_PATH=/path/to/chromium to use an existing browser.
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE = (process.env.BASE || "https://new-portfolio.ar-anupamsarkar.workers.dev").replace(/\/$/, "");
const OUT = path.resolve("public/shots");
const DESK = { width: 1280, height: 800 };
const MOB = { width: 390, height: 844 };

const manifest = { capturedAt: new Date().toISOString(), base: BASE, sets: {} };
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});

async function page(viewport, opts = {}) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2, colorScheme: "dark", ...opts });
  await ctx.addInitScript(() => { try { localStorage.setItem("theme", "dark"); } catch {} });
  return ctx.newPage();
}
async function shot(p, set, file, caption, extra = {}) {
  await p.waitForTimeout(600);
  await p.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: 78 });
  (manifest.sets[set] ||= []).push({ src: `shots/${file}`, caption, ...extra });
  console.log("captured", set, file);
}
const clickBtn = async (p, name) => {
  await p.getByRole("button", { name }).filter({ visible: true }).first().click({ timeout: 8000 });
  await p.waitForTimeout(1200);
};

await mkdir(OUT, { recursive: true });

// 1 · Synthetic usability testing — the full six-step flow in the live Lab
{
  const p = await page(DESK);
  await p.goto(`${BASE}/uxkpi-lab`, { waitUntil: "networkidle" });
  await shot(p, "synthetic", "lab-1-setup.jpg", "Setup: pick a project and see what needs attention");
  await clickBtn(p, "Resume setup");
  await clickBtn(p, "Continue to Upload");
  await clickBtn(p, "Load sample flow (PowerGrid billing)");
  await clickBtn(p, "Analyze flows");
  await p.waitForTimeout(3000);
  await shot(p, "synthetic", "lab-2-upload.jpg", "Upload: before-and-after screens, analysed into flows");
  await clickBtn(p, "Continue to Personas");
  await clickBtn(p, "Generate 5 personas");
  await p.waitForTimeout(3000);
  await shot(p, "synthetic", "lab-3-personas.jpg", "Personas: a generated panel, locked by a person before testing");
  await clickBtn(p, "Lock panel · Continue to Testing");
  await clickBtn(p, "Run Tests");
  await shot(p, "synthetic", "lab-4-testing.jpg", "Testing: choose the test types to run");
  await clickBtn(p, "Start Test Run");
  await p.waitForTimeout(20000);
  await shot(p, "synthetic", "lab-5-kpi.jpg", "KPI matrix: before versus after per persona, measured from 120 simulated sessions");
  await p.getByText("Report", { exact: true }).first().click().catch(() => {});
  await p.waitForTimeout(2500);
  await shot(p, "synthetic", "lab-6-report.jpg", "Report: issues ranked by measured severity, each with a recommended fix");
  await p.context().close();
}

// 2 · Portfolio agent — a real question, a real answer
{
  const p = await page(DESK);
  await p.goto(`${BASE}/index.html?mode=agent`, { waitUntil: "networkidle" });
  await p.evaluate(() => document.querySelectorAll(".reveal").forEach((e) => e.classList.add("in")));
  await shot(p, "agent", "agent-1-console.jpg", "Ask by typing or by voice call");
  await p.fill("#cinput", "What workflows does he run on a schedule?");
  await p.press("#cinput", "Enter");
  await p.waitForFunction(() => (document.getElementById("abody")?.innerText || "").trim().length > 80, null, { timeout: 30000 }).catch(() => {});
  await p.waitForTimeout(1500);
  await p.evaluate(() => { const a = document.getElementById("answer"); if (a) window.scrollTo(0, a.getBoundingClientRect().top + window.scrollY - 150); });
  await shot(p, "agent", "agent-2-answer.jpg", "A grounded answer, with the matching pages attached");
  await p.context().close();
}

// 3 · Scheduled workflow outputs — desktop and phone
for (const [set, url, label] of [
  ["daily", "samples/daily-ai-updates.html", "Daily AI Updates"],
  ["scout", "samples/ai-scout-designers.html", "AI Scout"],
]) {
  const d = await page(DESK);
  await d.goto(`${BASE}/${url}`, { waitUntil: "networkidle" });
  await shot(d, set, `${set}-1-top.jpg`, `${label}: the brief as it arrives`);
  await d.evaluate(() => window.scrollTo(0, 700));
  await shot(d, set, `${set}-2-scroll.jpg`, `${label}: every item carries its source`);
  await d.context().close();
  const m = await page(MOB, { isMobile: true, hasTouch: true });
  await m.goto(`${BASE}/${url}`, { waitUntil: "networkidle" });
  await shot(m, set, `${set}-3-phone.jpg`, `${label}: on a phone`, { phone: true });
  await m.context().close();
}

await browser.close();
await writeFile(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log("manifest written:", Object.fromEntries(Object.entries(manifest.sets).map(([k, v]) => [k, v.length])));
