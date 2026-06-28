const fs = require("fs");
const path = require("path");

const indexPath = path.join(__dirname, "..", "public", "index.html");
const html = fs.readFileSync(indexPath, "utf8");

for (const token of [
  "Competitive Brief",
  "Actual archive: 2026-06-17 to 2026-06-27",
  "Primary finding",
  "AWS is pushing OpenSearch Serverless into agentic developer workflows.",
  "What happened",
  "Why it matters",
  "Recommended response",
  "AWS OpenSearch Serverless remains the primary finding from the archive.",
  "Constructor and Bloomreach customer proof needs sales validation.",
  "AI search packaging is the repeated market pattern.",
  "Report history",
  "Data limits",
  "Archive is sparse",
  "Show collection details",
  "/archive/2026-06-20.md",
  "/archive/2026-06-27-weekly.md",
  "<base target=\"_blank\">",
  "noopener noreferrer"
]) {
  if (!html.includes(token)) {
    throw new Error(`Dashboard static seed is missing: ${token}`);
  }
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
