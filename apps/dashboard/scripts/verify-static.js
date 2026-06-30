const fs = require("fs");
const path = require("path");

const indexPath = path.join(__dirname, "..", "public", "index.html");
const html = fs.readFileSync(indexPath, "utf8");

for (const token of [
  "Competitive Brief",
  "Actual archive:",
  "Primary finding",
  "What happened",
  "Why it matters",
  "Recommended response",
  "Customer Proof Radar",
  "Narrative And Content Radar",
  "Decision Queue",
  "Suppressed Signals",
  "Report history",
  "Data limits",
  "Automated archive",
  "Show collection details",
  "archive/",
  "<base target=\"_blank\">",
  "noopener noreferrer"
]) {
  if (!html.includes(token)) {
    throw new Error(`Dashboard static seed is missing: ${token}`);
  }
}

const latestDataPath = path.join(__dirname, "..", "public", "data", "latest.json");
if (!fs.existsSync(latestDataPath)) {
  throw new Error("Dashboard data export is missing: data/latest.json");
}
const latestData = JSON.parse(fs.readFileSync(latestDataPath, "utf8"));
if (!latestData.report_count || latestData.report_count < 1) {
  throw new Error("Dashboard data export has no indexed reports.");
}
if (!latestData.archive_range || !latestData.reports || !latestData.reports.length) {
  throw new Error("Dashboard data export is missing archive metadata.");
}
if (latestData.semantic_dashboard !== "data/semantic-dashboard.json") {
  throw new Error("Dashboard latest.json is not wired to semantic-dashboard.json.");
}

const semanticDataPath = path.join(__dirname, "..", "public", "data", "semantic-dashboard.json");
if (!fs.existsSync(semanticDataPath)) {
  throw new Error("Dashboard semantic export is missing: data/semantic-dashboard.json");
}
const semanticData = JSON.parse(fs.readFileSync(semanticDataPath, "utf8"));
for (const key of [
  "daily_state",
  "weekly_state",
  "material_deltas",
  "suppressed_diagnostics",
  "source_health",
  "action_queue",
  "delivery_status",
  "coverage_limits"
]) {
  if (!(key in semanticData)) {
    throw new Error(`Dashboard semantic export is missing: ${key}`);
  }
}
if (!semanticData.coverage_limits || semanticData.coverage_limits.private_sources_connected !== false) {
  throw new Error("Dashboard semantic export must state public-source-only coverage limits.");
}

for (const token of [
  "Attention queue",
  "Mock findings",
  "Accept posture",
  "Assign review",
  "Ask for proof",
  "Archive count",
  "Collector context",
  "Other findings",
  "scorebox",
  "case_study"
]) {
  if (html.includes(token)) {
    throw new Error(`Dashboard static seed still contains retired UX copy: ${token}`);
  }
}

console.log("Dashboard static seed verified.");
