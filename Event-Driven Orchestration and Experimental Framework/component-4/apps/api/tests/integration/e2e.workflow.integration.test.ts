/**
// ─────────────────────────────────────────────────────────────────────────────
// Part 3.5: End-to-End Workflow Verification Tests
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Directly tests Workflows A through F defined in Part 3.5:
//   Workflow A: Create and retrieve an event (end-to-end data integrity)
//   Workflow B: Edit an event (partial update, invariant preservation)
//   Workflow C: Validation failure (rejection, no unintended persistence)
//   Workflow D: Lifecycle operations (cancellation, status transitions, deletion)
//   Workflow E: Missing event (not-found semantics and contract structure)
//   Workflow F: Database readiness and diagnostic security (health checks)
// ─────────────────────────────────────────────────────────────────────────────
*/

import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import request from "supertest";
import { app } from "../../src/app.js";
import { ScheduledEventModel } from "../../src/models/index.js";
import type { CreateScheduledEventInput, UpdateScheduledEventInput } from "@component4/shared";
import {
  isLiveIntegrationEnabled,
  setupIntegrationDatabase,
  cleanTestDatabase,
  teardownIntegrationDatabase,
} from "./test-db.js";

const isEnabled = isLiveIntegrationEnabled();
const testSuite = isEnabled ? describe : describe.skip;

testSuite("Part 3.5 End-to-End Workflow Verification (Live MongoDB Atlas)", () => {
  beforeAll(async () => {
    if (isEnabled) {
      await setupIntegrationDatabase();
    }
  });

  afterAll(async () => {
    if (isEnabled) {
      await teardownIntegrationDatabase();
    }
  });

  beforeEach(async () => {
    if (isEnabled) {
      await cleanTestDatabase();
    }
  });

  const baseInput: CreateScheduledEventInput = {
    eventName: "Semester Registration Gala",
    eventType: "REGISTRATION",
    description: "Annual multi-service course enrollment event",
    startTime: "2026-11-15T09:00:00Z",
    endTime: "2026-11-15T17:00:00Z",
    expectedLoad: "VERY_HIGH",
    priority: "CRITICAL",
    prewarmWindowMinutes: 60,
  };

  // ── Workflow A: Create and Retrieve an Event ────────────────────────────────
  describe("Workflow A: Create and Retrieve an Event", () => {
    it("persists a valid event in Atlas and retrieves it with consistent contract fields", async () => {
      // 1. Submit a valid event through API
      const createRes = await request(app)
        .post("/api/events")
        .send(baseInput)
        .expect(201);

      expect(createRes.body).toHaveProperty("event");
      const created = createRes.body.event;

      // 2. Confirm application-level eventId and default status
      expect(created.eventId).toMatch(/^evt_[a-zA-Z0-9_-]+$/);
      expect(created.status).toBe("SCHEDULED");
      expect(created.eventName).toBe(baseInput.eventName);
      expect(created.createdAt).toBeDefined();
      expect(created.updatedAt).toBeDefined();

      // 3. Confirm persistence in safe test database directly
      const atlasDoc = await ScheduledEventModel.findOne({ eventId: created.eventId }).exec();
      expect(atlasDoc).not.toBeNull();
      expect(atlasDoc?.eventName).toBe(baseInput.eventName);
      expect(atlasDoc?.status).toBe("SCHEDULED");
      expect(atlasDoc?.prewarmWindowMinutes).toBe(60);

      // 4. Retrieve event using application-level eventId
      const getRes = await request(app)
        .get(`/api/events/${created.eventId}`)
        .expect(200);

      // 5. Verify retrieved fields match stored fields exactly
      const retrieved = getRes.body.event;
      expect(retrieved.eventId).toBe(created.eventId);
      expect(retrieved.eventName).toBe(created.eventName);
      expect(retrieved.startTime).toBe(created.startTime);
      expect(retrieved.endTime).toBe(created.endTime);
      expect(retrieved.expectedLoad).toBe("VERY_HIGH");
      expect(retrieved.priority).toBe("CRITICAL");

      // Verify MongoDB internal fields are omitted
      expect((retrieved as Record<string, unknown>)["_id"]).toBeUndefined();
      expect((retrieved as Record<string, unknown>)["__v"]).toBeUndefined();
    });
  });

  // ── Workflow B: Edit an Event ───────────────────────────────────────────────
  describe("Workflow B: Edit an Event", () => {
    it("updates editable fields, updates updatedAt, and preserves unchanged fields", async () => {
      // 1. Create initial event
      const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
      const initial = createRes.body.event;

      // 2. Submit partial update to editable fields
      const updatePayload: UpdateScheduledEventInput = {
        eventName: "Semester Registration Gala (Extended)",
        description: "Updated description with extended capacity",
        expectedLoad: "HIGH",
        prewarmWindowMinutes: 90,
      };

      const patchRes = await request(app)
        .patch(`/api/events/${initial.eventId}`)
        .send(updatePayload)
        .expect(200);

      const updated = patchRes.body.event;

      // 3. Verify changed fields
      expect(updated.eventName).toBe("Semester Registration Gala (Extended)");
      expect(updated.description).toBe("Updated description with extended capacity");
      expect(updated.expectedLoad).toBe("HIGH");
      expect(updated.prewarmWindowMinutes).toBe(90);

      // 4. Verify unchanged fields preserved
      expect(updated.eventId).toBe(initial.eventId);
      expect(updated.eventType).toBe(initial.eventType);
      expect(updated.startTime).toBe(initial.startTime);
      expect(updated.endTime).toBe(initial.endTime);
      expect(updated.priority).toBe(initial.priority);
      expect(updated.status).toBe(initial.status);
      expect(updated.createdAt).toBe(initial.createdAt);

      // 5. Verify updatedAt timestamp advanced or equal
      expect(new Date(updated.updatedAt).getTime()).toBeGreaterThanOrEqual(
        new Date(initial.updatedAt).getTime()
      );

      // 6. Verify cross-field date window validation when updating single date
      const invalidDateRes = await request(app)
        .patch(`/api/events/${initial.eventId}`)
        .send({ startTime: "2026-11-15T18:00:00Z" }) // after endTime (17:00:00Z)
        .expect(400);

      expect(invalidDateRes.body.error).toBe("Bad Request");
    });
  });

  // ── Workflow C: Validation Failure ──────────────────────────────────────────
  describe("Workflow C: Validation Failure", () => {
    it("rejects invalid payloads, invalid date ranges, and system field injection", async () => {
      // 1. Invalid date range: endTime before startTime
      const invalidDateRes = await request(app)
        .post("/api/events")
        .send({
          ...baseInput,
          startTime: "2026-11-15T17:00:00Z",
          endTime: "2026-11-15T09:00:00Z",
        })
        .expect(400);

      expect(invalidDateRes.body.error).toBe("Bad Request");
      expect(invalidDateRes.body.issues).toBeDefined();

      // Confirm no invalid record was persisted in Atlas
      const count = await ScheduledEventModel.countDocuments();
      expect(count).toBe(0);

      // 2. Invalid enum value
      const invalidEnumRes = await request(app)
        .post("/api/events")
        .send({
          ...baseInput,
          expectedLoad: "SUPER_DUPER",
        })
        .expect(400);

      expect(invalidEnumRes.body.error).toBe("Bad Request");

      // 3. Attempting to inject system-managed status or eventId
      const injectionRes = await request(app)
        .post("/api/events")
        .send({
          ...baseInput,
          status: "COMPLETED",
          eventId: "EVT-HACKED",
        })
        .expect(400);

      expect(injectionRes.body.error).toBe("Bad Request");
    });
  });

  // ── Workflow D: Lifecycle Operations ────────────────────────────────────────
  describe("Workflow D: Lifecycle Operations", () => {
    it("handles cancellation, rejects invalid transitions, and executes permanent deletion", async () => {
      // 1. Create test event
      const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
      const eventId = createRes.body.event.eventId;

      // 2. Perform supported cancellation
      const cancelRes = await request(app)
        .post(`/api/events/${eventId}/cancel`)
        .expect(200);

      expect(cancelRes.body.event.status).toBe("CANCELLED");

      // 3. Verify in Atlas
      const cancelledDoc = await ScheduledEventModel.findOne({ eventId }).exec();
      expect(cancelledDoc?.status).toBe("CANCELLED");

      // 4. Verify invalid transition: CANCELLED cannot be cancelled again
      const conflictRes = await request(app)
        .post(`/api/events/${eventId}/cancel`)
        .expect(409);

      expect(conflictRes.body.error).toBe("Conflict");
      expect(conflictRes.body.message).toContain("already CANCELLED");

      // 5. Delete event permanently
      const deleteRes = await request(app)
        .delete(`/api/events/${eventId}`)
        .expect(200);

      expect(deleteRes.body.success).toBe(true);
      expect(deleteRes.body.eventId).toBe(eventId);

      // 6. Verify absence in Atlas
      const deletedDoc = await ScheduledEventModel.findOne({ eventId }).exec();
      expect(deletedDoc).toBeNull();

      // 7. Verify subsequent GET returns 404
      await request(app).get(`/api/events/${eventId}`).expect(404);
    });
  });

  // ── Workflow E: Missing Event ───────────────────────────────────────────────
  describe("Workflow E: Missing Event", () => {
    it("returns consistent 404 envelopes across GET, PATCH, DELETE, and CANCEL", async () => {
      const nonExistentId = "evt_non_existent_999";

      // GET missing
      const getRes = await request(app).get(`/api/events/${nonExistentId}`).expect(404);
      expect(getRes.body.error).toBe("Not Found");
      expect(getRes.body.message).toContain(nonExistentId);

      // PATCH missing
      const patchRes = await request(app)
        .patch(`/api/events/${nonExistentId}`)
        .send({ eventName: "Ghost Update" })
        .expect(404);
      expect(patchRes.body.error).toBe("Not Found");

      // DELETE missing
      const deleteRes = await request(app).delete(`/api/events/${nonExistentId}`).expect(404);
      expect(deleteRes.body.error).toBe("Not Found");

      // CANCEL missing
      const cancelRes = await request(app).post(`/api/events/${nonExistentId}/cancel`).expect(404);
      expect(cancelRes.body.error).toBe("Not Found");
    });
  });

  // ── Workflow F: Database Readiness & Diagnostic Security ────────────────────
  describe("Workflow F: Database Readiness & Diagnostic Security", () => {
    it("reports healthy readiness without leaking connection strings or credentials", async () => {
      const healthRes = await request(app).get("/api/health").expect(200);
      expect(healthRes.body.status).toBe("ok");

      const readyRes = await request(app).get("/api/health/ready").expect(200);
      expect(readyRes.body.status).toBe("ok");
      expect(readyRes.body.database).toBe("connected");

      // Ensure no passwords, URIs, or secrets appear in response payload
      const responseStr = JSON.stringify(readyRes.body);
      expect(responseStr).not.toContain("mongodb+srv://");
      expect(responseStr).not.toContain("password");
    });
  });
});
