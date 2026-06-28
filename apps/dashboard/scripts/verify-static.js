const fs = require("fs");
const path = require("path");

const indexPath = path.join(__dirname, "..", "public", "index.html");
const html = fs.readFileSync(indexPath, "utf8");

for (const token of [
  "Competitive Brief",
  "Actual archive: 2026-06-17 to 2026-06-27",
  "The strongest actual finding is AWS OpenSearch pressure",
  "AWS OpenSearch Serverless is the strongest strategic threat found so far.",
  "Constructor and Bloomreach customer proof needs sales validation.",
  "AI search packaging is the repeated market pattern.",
  "Report history",
  "Archive is sparse",
  "/archive/2026-06-20.md",
  "/archive/2026-06-27-weekly.md",
  "<base target=\"_blank\">",
  "noopener noreferrer"
]) {
  if (!html.includes(token)) {
    throw new Error(`Dashboard static seed is missing: ${token}`);
  }
}

console.log("Dashboard static seed verified.");
