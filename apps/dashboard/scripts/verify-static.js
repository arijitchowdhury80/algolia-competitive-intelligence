const fs = require("fs");
const path = require("path");

const indexPath = path.join(__dirname, "..", "public", "index.html");
const html = fs.readFileSync(indexPath, "utf8");

for (const token of [
  "Competitive Brief",
  "Actual archive: 2026-06-17 to 2026-06-27",
  "Primary finding",
  "Constructor customer proof changed needs validation.",
  "What happened",
  "Why it matters",
  "Recommended response",
  "The pattern is named AI search packaging.",
  "Report history",
  "Data limits",
  "Automated archive",
  "Show collection details",
  "archive/2026-06-20.md",
  "archive/2026-06-27-weekly.md",
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

for (const token of [
  "Attention queue",
  "Mock findings",
  "Accept posture",
  "Assign review",
  "Ask for proof",
  "Archive count",
  "Collector context",
  "scorebox"
]) {
  if (html.includes(token)) {
    throw new Error(`Dashboard static seed still contains retired UX copy: ${token}`);
  }
}

console.log("Dashboard static seed verified.");
