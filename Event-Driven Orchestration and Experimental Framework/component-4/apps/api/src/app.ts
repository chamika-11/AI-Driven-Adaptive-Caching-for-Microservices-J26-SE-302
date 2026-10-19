import express from "express";
import cors from "cors";
import helmet from "helmet";
import { healthRouter, eventRouter, docsRouter } from "./routes/index.js";
import { errorHandler } from "./middleware/index.js";

export const app = express();

// ── Global middleware ────────────────────────────────────────────────────────
app.use(helmet());
app.use(cors());
app.use(express.json());

// ── Routes ───────────────────────────────────────────────────────────────────
app.use("/api", healthRouter);
app.use("/api/events", eventRouter);
app.use("/api/docs", docsRouter);

// ── Centralized Error Handling Middleware ─────────────────────────────────────
app.use(errorHandler);

