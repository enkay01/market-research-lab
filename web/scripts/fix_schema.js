import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const schemaPath = path.resolve(__dirname, "../src/api/schema.ts");

if (fs.existsSync(schemaPath)) {
  let content = fs.readFileSync(schemaPath, "utf-8");
  content = content
    .replace(/^(\s*)"JsonValue-Input":[\s\S]*?\} \| null;/m, '$1"JsonValue-Input": unknown;')
    .replace(/^(\s*)"JsonValue-Output":[\s\S]*?\} \| null;/m, '$1"JsonValue-Output": unknown;');
  fs.writeFileSync(schemaPath, content, "utf-8");
}
