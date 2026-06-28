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

for (const token of [
  "Attention queue",
  "Mock findings",
  "Accept posture",
  "Assign review",
  "Ask for proof",
  "Archive count",
  "Collector context",
  "scorebox",
  "case_study"
]) {
  if (html.includes(token)) {
    throw new Error(`Dashboard static seed still contains retired UX copy: ${token}`);
  }
}

console.log("Dashboard static seed verified.");
