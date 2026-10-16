import "dotenv/config";
import { app } from "./app.js";

const PORT = parseInt(process.env["API_PORT"] ?? "4004", 10);
const HOST = process.env["API_HOST"] ?? "0.0.0.0";

app.listen(PORT, HOST, () => {
  console.log(`[Component 4 API] listening on http://${HOST}:${PORT}`);
});
