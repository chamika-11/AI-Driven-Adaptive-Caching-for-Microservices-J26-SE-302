/**
// ─────────────────────────────────────────────────────────────────────────────
// Event Management REST API Unit & Route Tests (Part 3.1)
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Tests Express routes, controllers, error-handling middleware, and contract compliance
// using Supertest with controlled mock dependencies.
// ─────────────────────────────────────────────────────────────────────────────
*/

import { describe, it, expect, vi, beforeEach } from "vitest";
import request from "supertest";
import express from "express";
import { createEventRouter } from "../src/routes/event.routes.js";
import { EventController } from "../src/controllers/event.controller.js";
import { EventService } from "../src/services/event.service.js";
import { errorHandler } from "../src/middleware/error-handler.js";
import {
  type IEventRepository,
  RepositoryDuplicateKeyError,
  RepositoryDatabaseError,
} from "../src/repositories/index.js";
import type {
  ScheduledEvent,
  CreateScheduledEventInput,
  EventListResponse,
} from "@component4/shared";

function createMockRepository(): IEventRepository {
  let storedEvents: ScheduledEvent[] = [];

  return {
    create: vi.fn().mockImplementation(async (input: CreateScheduledEventInput, idOverride?: string) => {
      const eventId = idOverride ?? `evt_${Math.random().toString(36).substring(2, 9)}`;
      const existing = storedEvents.find((e) => e.eventId === eventId);
      if (existing) {
        throw new RepositoryDuplicateKeyError("eventId", eventId);
      }

      const event: ScheduledEvent = {
        eventId,
        eventName: input.eventName,
        eventType: input.eventType,
        description: input.description,
        startTime: new Date(input.startTime).toISOString(),
        endTime: new Date(input.endTime).toISOString(),
        expectedLoad: input.expectedLoad,
        priority: input.priority,
        prewarmWindowMinutes: input.prewarmWindowMinutes,
        status: "SCHEDULED",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      storedEvents.push(event);
      return event;
    }),

    findById: vi.fn().mockImplementation(async (eventId: string) => {
      return storedEvents.find((e) => e.eventId === eventId) ?? null;
    }),

    list: vi.fn().mockImplementation(async (query = {}) => {
      let filtered = [...storedEvents];
      if (query.status) {
        filtered = filtered.filter((e) => e.status === query.status);
      }
      if (query.eventType) {
        filtered = filtered.filter((e) => e.eventType === query.eventType);
      }
      if (query.priority) {
        filtered = filtered.filter((e) => e.priority === query.priority);
      }

      const page = query.page ?? 1;
      const limit = query.limit ?? 20;
      const total = filtered.length;
      const totalPages = total === 0 ? 0 : Math.ceil(total / limit);

      const skip = (page - 1) * limit;
      const paged = filtered.slice(skip, skip + limit);

      const response: EventListResponse = {
        events: paged,
        pagination: {
          total,
          page,
          limit,
          totalPages,
        },
      };
      return response;
    }),

    update: vi.fn().mockImplementation(async (eventId: string, input: Record<string, unknown>) => {
      const index = storedEvents.findIndex((e) => e.eventId === eventId);
      if (index === -1) {
        return null;
      }
      const existing = storedEvents[index];

      const startTime = input.startTime ? new Date(input.startTime as string).toISOString() : existing.startTime;
      const endTime = input.endTime ? new Date(input.endTime as string).toISOString() : existing.endTime;

      if (new Date(endTime).getTime() <= new Date(startTime).getTime()) {
        const { RepositoryValidationError } = await import("../src/repositories/index.js");
        throw new RepositoryValidationError("endTime must be strictly later than startTime", [
          "endTime: endTime must be strictly later than startTime",
        ]);
      }

      const updated: ScheduledEvent = {
        ...existing,
        ...input,
        startTime,
        endTime,
        updatedAt: new Date().toISOString(),
      };
      storedEvents[index] = updated;
      return updated;
    }),

    updateStatus: vi.fn().mockImplementation(async (eventId: string, newStatus: ScheduledEvent["status"]) => {
      const index = storedEvents.findIndex((e) => e.eventId === eventId);
      if (index === -1) return null;
      storedEvents[index].status = newStatus;
      return storedEvents[index];
    }),

    delete: vi.fn().mockImplementation(async (eventId: string) => {
      const initialLength = storedEvents.length;
      storedEvents = storedEvents.filter((e) => e.eventId !== eventId);
      return storedEvents.length < initialLength;
    }),
  };
}

describe("Event Management REST API Routes (Unit & Route Tests)", () => {
  let app: express.Express;
  let mockRepo: IEventRepository;

  const validEventPayload: CreateScheduledEventInput = {
    eventName: "Campus Registration Day",
    eventType: "REGISTRATION",
    description: "Annual course registration event",
    startTime: "2026-11-20T08:00:00Z",
    endTime: "2026-11-20T18:00:00Z",
    expectedLoad: "HIGH",
    priority: "HIGH",
    prewarmWindowMinutes: 45,
  };

  beforeEach(() => {
    mockRepo = createMockRepository();
    const service = new EventService(mockRepo);
    const controller = new EventController(service);
    const router = createEventRouter(controller);

    app = express();
    app.use(express.json());
    app.use("/api/events", router);
    app.use(errorHandler);
  });

  // ── 4.1 POST /api/events (Create) ──────────────────────────────────────────

  describe("POST /api/events", () => {
    it("should create an event and return 201 with EventResponse", async () => {
      const res = await request(app)
        .post("/api/events")
        .send(validEventPayload)
        .expect(201);

      expect(res.body).toHaveProperty("event");
      const event = res.body.event;
      expect(event.eventId).toBeDefined();
      expect(event.eventName).toBe(validEventPayload.eventName);
      expect(event.status).toBe("SCHEDULED");
      expect(event.startTime).toBe(new Date(validEventPayload.startTime).toISOString());
      expect(event.createdAt).toBeDefined();
    });

    it("should return 400 Bad Request when required field is missing", async () => {
      const invalid = { ...validEventPayload };
      delete (invalid as Record<string, unknown>).eventName;

      const res = await request(app)
        .post("/api/events")
        .send(invalid)
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.issues).toBeDefined();
      expect(res.body.issues.some((i: string) => i.includes("eventName"))).toBe(true);
    });

    it("should return 400 Bad Request when client sends system-managed fields", async () => {
      const malicious = {
        ...validEventPayload,
        eventId: "EVT-HACK-001",
        status: "COMPLETED",
      };

      const res = await request(app)
        .post("/api/events")
        .send(malicious)
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.issues.some((i: string) => i.toLowerCase().includes("unrecognized"))).toBe(true);
    });

    it("should return 400 Bad Request when endTime <= startTime", async () => {
      const invalidDates = {
        ...validEventPayload,
        startTime: "2026-11-20T18:00:00Z",
        endTime: "2026-11-20T08:00:00Z",
      };

      const res = await request(app)
        .post("/api/events")
        .send(invalidDates)
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.issues.some((i: string) => i.includes("endTime"))).toBe(true);
    });

    it("should return 409 Conflict when duplicate key collision occurs", async () => {
      // Force repository duplicate error
      vi.spyOn(mockRepo, "create").mockRejectedValueOnce(
        new RepositoryDuplicateKeyError("eventId", "EVT-DUPLICATE-001")
      );

      const res = await request(app)
        .post("/api/events")
        .send(validEventPayload)
        .expect(409);

      expect(res.body.error).toBe("Conflict");
      expect(res.body.message).toContain("EVT-DUPLICATE-001");
    });
  });

  // ── 4.2 GET /api/events (List) ─────────────────────────────────────────────

  describe("GET /api/events", () => {
    beforeEach(async () => {
      await mockRepo.create(
        {
          ...validEventPayload,
          eventName: "Event 1",
          eventType: "REGISTRATION",
          priority: "HIGH",
        },
        "EVT-001"
      );
      await mockRepo.create(
        {
          ...validEventPayload,
          eventName: "Event 2",
          eventType: "RESULT_RELEASE",
          priority: "CRITICAL",
        },
        "EVT-002"
      );
    });

    it("should list events with default pagination and return 200 OK", async () => {
      const res = await request(app).get("/api/events").expect(200);

      expect(res.body).toHaveProperty("events");
      expect(res.body).toHaveProperty("pagination");
      expect(res.body.events).toHaveLength(2);
      expect(res.body.pagination.total).toBe(2);
      expect(res.body.pagination.page).toBe(1);
      expect(res.body.pagination.limit).toBe(20);
    });

    it("should filter by eventType", async () => {
      const res = await request(app)
        .get("/api/events?eventType=REGISTRATION")
        .expect(200);

      expect(res.body.events).toHaveLength(1);
      expect(res.body.events[0].eventType).toBe("REGISTRATION");
    });

    it("should filter by priority", async () => {
      const res = await request(app)
        .get("/api/events?priority=CRITICAL")
        .expect(200);

      expect(res.body.events).toHaveLength(1);
      expect(res.body.events[0].priority).toBe("CRITICAL");
    });

    it("should return 400 Bad Request for invalid enum filter query", async () => {
      const res = await request(app)
        .get("/api/events?status=INVALID_STATUS")
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.issues.some((i: string) => i.includes("status"))).toBe(true);
    });

    it("should return 400 Bad Request for inverted date range query", async () => {
      const res = await request(app)
        .get("/api/events?startDateFrom=2026-11-25T00:00:00Z&startDateTo=2026-11-10T00:00:00Z")
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.issues.some((i: string) => i.includes("startDateTo"))).toBe(true);
    });
  });

  // ── 4.3 GET /api/events/:eventId (Get by ID) ───────────────────────────────

  describe("GET /api/events/:eventId", () => {
    it("should return 200 OK with event when found", async () => {
      const created = await mockRepo.create(validEventPayload, "EVT-FIND-001");

      const res = await request(app)
        .get(`/api/events/${created.eventId}`)
        .expect(200);

      expect(res.body).toHaveProperty("event");
      expect(res.body.event.eventId).toBe("EVT-FIND-001");
      expect(res.body.event.eventName).toBe(validEventPayload.eventName);
    });

    it("should return 404 Not Found when event does not exist", async () => {
      const res = await request(app)
        .get("/api/events/EVT-NON-EXISTENT")
        .expect(404);

      expect(res.body.error).toBe("Not Found");
      expect(res.body.message).toContain("EVT-NON-EXISTENT");
    });
  });

  // ── 4.4 PATCH /api/events/:eventId (Update) ────────────────────────────────

  describe("PATCH /api/events/:eventId", () => {
    beforeEach(async () => {
      await mockRepo.create(validEventPayload, "EVT-UPDATE-001");
    });

    it("should update event and return 200 OK with updated EventResponse", async () => {
      const res = await request(app)
        .patch("/api/events/EVT-UPDATE-001")
        .send({ eventName: "Renamed Annual Registration" })
        .expect(200);

      expect(res.body.event.eventName).toBe("Renamed Annual Registration");
      expect(res.body.event.eventType).toBe("REGISTRATION"); // preserved
    });

    it("should return 400 Bad Request on empty update body", async () => {
      const res = await request(app)
        .patch("/api/events/EVT-UPDATE-001")
        .send({})
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.issues.some((i: string) => i.includes("empty"))).toBe(true);
    });

    it("should return 400 Bad Request when attempting to modify status via general PATCH", async () => {
      const res = await request(app)
        .patch("/api/events/EVT-UPDATE-001")
        .send({ status: "COMPLETED" })
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.issues.some((i: string) => i.toLowerCase().includes("unrecognized"))).toBe(true);
    });

    it("should return 400 Bad Request when update results in invalid datetime range", async () => {
      const res = await request(app)
        .patch("/api/events/EVT-UPDATE-001")
        .send({
          startTime: "2026-11-20T19:00:00Z",
          endTime: "2026-11-20T17:00:00Z",
        })
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
    });

    it("should return 404 Not Found when updating a non-existent event", async () => {
      const res = await request(app)
        .patch("/api/events/EVT-GHOST")
        .send({ eventName: "New Name" })
        .expect(404);

      expect(res.body.error).toBe("Not Found");
    });
  });

  // ── 4.5 DELETE /api/events/:eventId (Delete) ───────────────────────────────

  describe("DELETE /api/events/:eventId", () => {
    it("should delete event and return 200 OK with confirmation", async () => {
      await mockRepo.create(validEventPayload, "EVT-DELETE-001");

      const res = await request(app)
        .delete("/api/events/EVT-DELETE-001")
        .expect(200);

      expect(res.body.success).toBe(true);
      expect(res.body.eventId).toBe("EVT-DELETE-001");

      // Verify no longer found
      await request(app).get("/api/events/EVT-DELETE-001").expect(404);
    });

    it("should return 404 Not Found when deleting non-existent event", async () => {
      const res = await request(app)
        .delete("/api/events/EVT-NON-EXISTENT")
        .expect(404);

      expect(res.body.error).toBe("Not Found");
    });
  });

  // ── 4.6 POST /api/events/:eventId/cancel (Cancel Event Lifecycle) ───────────

  describe("POST /api/events/:eventId/cancel", () => {
    it("should cancel a SCHEDULED event and return 200 OK with updated event", async () => {
      await mockRepo.create(validEventPayload, "EVT-CANCEL-001");

      const res = await request(app)
        .post("/api/events/EVT-CANCEL-001/cancel")
        .expect(200);

      expect(res.body.event).toBeDefined();
      expect(res.body.event.eventId).toBe("EVT-CANCEL-001");
      expect(res.body.event.status).toBe("CANCELLED");

      // Verify status persisted
      const getRes = await request(app).get("/api/events/EVT-CANCEL-001").expect(200);
      expect(getRes.body.event.status).toBe("CANCELLED");
    });

    it("should reject cancellation of an already CANCELLED event with 409 Conflict", async () => {
      await mockRepo.create(validEventPayload, "EVT-CANCEL-002");
      await request(app).post("/api/events/EVT-CANCEL-002/cancel").expect(200);

      const res = await request(app)
        .post("/api/events/EVT-CANCEL-002/cancel")
        .expect(409);

      expect(res.body.error).toBe("Conflict");
      expect(res.body.message).toContain("already CANCELLED");
    });

    it("should reject cancellation of a COMPLETED event with 409 Conflict", async () => {
      await mockRepo.create(validEventPayload, "EVT-CANCEL-003");
      await mockRepo.updateStatus("EVT-CANCEL-003", "COMPLETED");

      const res = await request(app)
        .post("/api/events/EVT-CANCEL-003/cancel")
        .expect(409);

      expect(res.body.error).toBe("Conflict");
      expect(res.body.message).toContain("already COMPLETED");
    });

    it("should reject cancellation of a PROCESSING event with 409 Conflict", async () => {
      await mockRepo.create(validEventPayload, "EVT-CANCEL-004");
      await mockRepo.updateStatus("EVT-CANCEL-004", "PROCESSING");

      const res = await request(app)
        .post("/api/events/EVT-CANCEL-004/cancel")
        .expect(409);

      expect(res.body.error).toBe("Conflict");
      expect(res.body.message).toContain("currently PROCESSING");
    });

    it("should return 404 Not Found when cancelling a non-existent event", async () => {
      const res = await request(app)
        .post("/api/events/EVT-NON-EXISTENT/cancel")
        .expect(404);

      expect(res.body.error).toBe("Not Found");
      expect(res.body.message).toContain("EVT-NON-EXISTENT");
    });
  });

  // ── 5. Error Middleware & Infrastructure Failures ───────────────────────────

  describe("5. Error Middleware & Diagnostics", () => {
    it("should return 503 Service Unavailable when repository throws database error", async () => {
      vi.spyOn(mockRepo, "findById").mockRejectedValueOnce(
        new RepositoryDatabaseError("Atlas cluster connection lost mongodb+srv://admin:secret@host")
      );

      const res = await request(app)
        .get("/api/events/EVT-ANY")
        .expect(503);

      expect(res.body.error).toBe("Service Unavailable");
      expect(res.body.message).toBe("Database service is temporarily unavailable");
      // Credentials must never be leaked
      expect(JSON.stringify(res.body)).not.toContain("secret");
      expect(JSON.stringify(res.body)).not.toContain("admin");
    });

    it("should return 400 Bad Request on malformed JSON payload", async () => {
      const res = await request(app)
        .post("/api/events")
        .set("Content-Type", "application/json")
        .send("{ broken json content")
        .expect(400);

      expect(res.body.error).toBe("Bad Request");
      expect(res.body.message).toContain("Malformed JSON");
    });
  });
});
