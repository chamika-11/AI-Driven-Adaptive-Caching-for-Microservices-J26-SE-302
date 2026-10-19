// ─────────────────────────────────────────────────────────────────────────────
// Async Route Handler Wrapper — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Catches unhandled promise rejections in Express 4 controller functions
// and forwards them to the centralized error-handling middleware.
// ─────────────────────────────────────────────────────────────────────────────

import type { Request, Response, NextFunction, RequestHandler } from "express";

export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<unknown>
): RequestHandler {
  return (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}
