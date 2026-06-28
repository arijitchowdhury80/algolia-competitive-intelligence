const fs = require("fs");
const path = require("path");

const indexPath = path.join(__dirname, "..", "public", "index.html");
const html = fs.readFileSync(indexPath, "utf8");

for (const token of [
  "CI Command Center",
  "Latest daily",
  "Latest weekly",
  "Source health and collector strategy",
  "Actions",
  "Archive"
]) {
  if (!html.includes(token)) {
    throw new Error(`Dashboard static seed is missing: ${token}`);
  }
}

console.log("Dashboard static seed verified.");

