// ─────────────────────────────────────────────────────────────────────────────
// Server Entry Point — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Loads environment, connects to MongoDB Atlas, and starts the HTTP listener.
// ─────────────────────────────────────────────────────────────────────────────

import path from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";

// In a monorepo setup, prioritize root .env then local apps/api/.env
const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, "../../../.env") });
dotenv.config({ path: path.resolve(__dirname, "../.env") });
dotenv.config();

import { startServer } from "./server.js";

// Execute startup sequence when launched as primary process
startServer().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`[Fatal Startup Error] API server failed to start: ${message}`);
  process.exit(1);
});

