// ─────────────────────────────────────────────────────────────────────────────
// Event Management Routes — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Mount path: /api/events
// ─────────────────────────────────────────────────────────────────────────────

import { Router } from "express";
import { asyncHandler } from "../middleware/index.js";
import { EventController } from "../controllers/index.js";

/**
 * Factory creating an Express router for Event Management endpoints.
 * Supports controller dependency injection for testing.
 */
export function createEventRouter(controller: EventController = new EventController()): Router {
  const router = Router();

  router.post("/", asyncHandler(controller.create));
  router.get("/", asyncHandler(controller.list));
  router.get("/:eventId", asyncHandler(controller.getById));
  router.patch("/:eventId", asyncHandler(controller.update));
  router.post("/:eventId/cancel", asyncHandler(controller.cancel));
  router.delete("/:eventId", asyncHandler(controller.delete));

  return router;
}

export const eventRouter = createEventRouter();
