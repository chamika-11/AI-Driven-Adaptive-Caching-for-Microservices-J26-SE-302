// ─────────────────────────────────────────────────────────────────────────────
// Health & Readiness Routes — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Endpoints:
//   - GET /api/health       : Process liveness probe (indicates Node/Express process is running).
//   - GET /api/health/ready : Service readiness probe (verifies active MongoDB connection).
//
// Security: Never returns credentials, connection strings, host details, or raw stack traces.
// ─────────────────────────────────────────────────────────────────────────────

import { Router, type Request, type Response } from "express";
import type { HealthCheckResponse } from "@component4/shared";
import { isDatabaseConnected } from "../infrastructure/database/index.js";

export const healthRouter = Router();

/**
 * Liveness Probe.
 * Indicates that the Node.js Express process is alive and responsive.
 */
healthRouter.get("/health", (_req: Request, res: Response) => {
  const body: HealthCheckResponse = {
    status: "ok",
    component: "component-4-api",
    version: "0.1.0",
    timestamp: new Date().toISOString(),
  };
  res.status(200).json(body);
});

/**
 * Readiness Probe.
 * Indicates whether the API is fully ready to process business traffic (MongoDB Atlas connected).
 * Returns HTTP 200 if connected, or HTTP 503 if the database is disconnected or degraded.
 */
healthRouter.get("/health/ready", (_req: Request, res: Response) => {
  const connected = isDatabaseConnected();
  const statusCode = connected ? 200 : 503;

  res.status(statusCode).json({
    status: connected ? "ok" : "degraded",
    component: "component-4-api",
    database: connected ? "connected" : "disconnected",
    timestamp: new Date().toISOString(),
  });
});
