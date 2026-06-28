const fs = require("fs");
const path = require("path");

const indexPath = path.join(__dirname, "..", "public", "index.html");
const html = fs.readFileSync(indexPath, "utf8");

for (const token of [
  "Weekly brief",
  "Start here",
  "Review two areas. Do not update battlecards yet.",
  "Next actions",
  "Show proof",
  "Proof behind the brief",
  "Data quality",
  "Latest daily",
  "Latest weekly"
]) {
  if (!html.includes(token)) {
    throw new Error(`Dashboard static seed is missing: ${token}`);
  }
}

console.log("Dashboard static seed verified.");
