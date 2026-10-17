import { Router, type Request, type Response } from "express";
import type { HealthCheckResponse } from "@component4/shared";

export const healthRouter = Router();

healthRouter.get("/health", (_req: Request, res: Response) => {
  const body: HealthCheckResponse = {
    status: "ok",
    component: "component-4-api",
    version: "0.1.0",
    timestamp: new Date().toISOString(),
  };
  res.json(body);
});
