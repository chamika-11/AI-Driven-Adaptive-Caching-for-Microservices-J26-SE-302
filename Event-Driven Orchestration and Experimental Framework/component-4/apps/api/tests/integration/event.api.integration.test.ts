/**
// ─────────────────────────────────────────────────────────────────────────────
// Event Management Live HTTP REST API Integration Tests (Part 3.1)
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Tests complete HTTP stack (Express -> Controller -> Service -> Repository -> Atlas)
// against the isolated test database 'component4_test'.
// ─────────────────────────────────────────────────────────────────────────────
*/

import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import request from "supertest";
import { app } from "../../src/app.js";
import { ScheduledEventModel } from "../../src/models/index.js";
import type { CreateScheduledEventInput } from "@component4/shared";
import {
  isLiveIntegrationEnabled,
  setupIntegrationDatabase,
  cleanTestDatabase,
  teardownIntegrationDatabase,
} from "./test-db.js";

const isEnabled = isLiveIntegrationEnabled();
const testSuite = isEnabled ? describe : describe.skip;

testSuite("Event Management REST API Live Integration Tests (Atlas)", () => {
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
    eventName: "Campus Registration Day",
    eventType: "REGISTRATION",
    description: "Annual student registration",
    startTime: "2026-11-20T08:00:00Z",
    endTime: "2026-11-20T18:00:00Z",
    expectedLoad: "HIGH",
    priority: "HIGH",
    prewarmWindowMinutes: 45,
  };

  it("POST /api/events -> should create event in MongoDB Atlas and return 201", async () => {
    const res = await request(app)
      .post("/api/events")
      .send(baseInput)
      .expect(201);

    expect(res.body).toHaveProperty("event");
    const event = res.body.event;
    expect(event.eventId).toBeDefined();
    expect(event.eventName).toBe(baseInput.eventName);
    expect(event.status).toBe("SCHEDULED");

    // Verify in MongoDB Atlas directly
    const doc = await ScheduledEventModel.findOne({ eventId: event.eventId }).exec();
    expect(doc).not.toBeNull();
    expect(doc?.eventName).toBe(baseInput.eventName);
  });

  it("GET /api/events -> should retrieve paginated events from Atlas", async () => {
    // Create 3 events
    await request(app).post("/api/events").send({ ...baseInput, eventName: "Event 1" }).expect(201);
    await request(app).post("/api/events").send({ ...baseInput, eventName: "Event 2" }).expect(201);
    await request(app).post("/api/events").send({ ...baseInput, eventName: "Event 3" }).expect(201);

    const res = await request(app).get("/api/events?page=1&limit=2").expect(200);

    expect(res.body.events).toHaveLength(2);
    expect(res.body.pagination.total).toBe(3);
    expect(res.body.pagination.totalPages).toBe(2);
  });

  it("GET /api/events/:eventId -> should retrieve single event", async () => {
    const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
    const eventId = createRes.body.event.eventId;

    const res = await request(app).get(`/api/events/${eventId}`).expect(200);
    expect(res.body.event.eventId).toBe(eventId);
    expect(res.body.event.eventName).toBe(baseInput.eventName);
  });

  it("PATCH /api/events/:eventId -> should update event in Atlas", async () => {
    const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
    const eventId = createRes.body.event.eventId;

    const updateRes = await request(app)
      .patch(`/api/events/${eventId}`)
      .send({ eventName: "Updated Registration Day" })
      .expect(200);

    expect(updateRes.body.event.eventName).toBe("Updated Registration Day");

    // Verify in MongoDB Atlas
    const doc = await ScheduledEventModel.findOne({ eventId }).exec();
    expect(doc?.eventName).toBe("Updated Registration Day");
  });

  it("DELETE /api/events/:eventId -> should delete event from Atlas", async () => {
    const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
    const eventId = createRes.body.event.eventId;

    const deleteRes = await request(app).delete(`/api/events/${eventId}`).expect(200);
    expect(deleteRes.body.success).toBe(true);
    expect(deleteRes.body.eventId).toBe(eventId);

    // Verify no longer in Atlas
    const doc = await ScheduledEventModel.findOne({ eventId }).exec();
    expect(doc).toBeNull();
  });

  it("POST /api/events/:eventId/cancel -> should cancel scheduled event in Atlas and return 200", async () => {
    const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
    const eventId = createRes.body.event.eventId;

    const cancelRes = await request(app)
      .post(`/api/events/${eventId}/cancel`)
      .expect(200);

    expect(cancelRes.body.event.status).toBe("CANCELLED");
    expect(cancelRes.body.event.eventId).toBe(eventId);

    // Verify in Atlas
    const doc = await ScheduledEventModel.findOne({ eventId }).exec();
    expect(doc?.status).toBe("CANCELLED");
  });

  it("POST /api/events/:eventId/cancel -> should reject cancellation of already cancelled event with 409 Conflict", async () => {
    const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
    const eventId = createRes.body.event.eventId;

    // First cancellation succeeds
    await request(app).post(`/api/events/${eventId}/cancel`).expect(200);

    // Second cancellation rejected
    const conflictRes = await request(app)
      .post(`/api/events/${eventId}/cancel`)
      .expect(409);

    expect(conflictRes.body.error).toBe("Conflict");
    expect(conflictRes.body.message).toContain("already CANCELLED");
  });

  it("POST /api/events/:eventId/cancel -> should return 404 when cancelling non-existent event", async () => {
    const res = await request(app)
      .post("/api/events/EVT-NON-EXISTENT/cancel")
      .expect(404);

    expect(res.body.error).toBe("Not Found");
    expect(res.body.message).toContain("EVT-NON-EXISTENT");
  });

  it("PATCH /api/events/:eventId -> should reject attempt to overwrite system-managed fields with 400 Bad Request", async () => {
    const createRes = await request(app).post("/api/events").send(baseInput).expect(201);
    const eventId = createRes.body.event.eventId;

    const res = await request(app)
      .patch(`/api/events/${eventId}`)
      .send({ status: "COMPLETED", eventId: "EVT-HACKED" })
      .expect(400);

    expect(res.body.error).toBe("Bad Request");
    expect(res.body.issues).toBeDefined();

    // Verify original event unmodified in Atlas
    const doc = await ScheduledEventModel.findOne({ eventId }).exec();
    expect(doc?.status).toBe("SCHEDULED");
    expect(doc?.eventId).toBe(eventId);
  });

  it("POST /api/events -> should reject invalid date range (endTime <= startTime) with 400 Bad Request", async () => {
    const invalidInput = {
      ...baseInput,
      startTime: "2026-11-20T18:00:00Z",
      endTime: "2026-11-20T08:00:00Z", // end before start
    };

    const res = await request(app)
      .post("/api/events")
      .send(invalidInput)
      .expect(400);

    expect(res.body.error).toBe("Bad Request");
    expect(res.body.issues).toBeDefined();
  });

  it("GET /api/events/:eventId -> should return 404 for non-existent event", async () => {
    const res = await request(app).get("/api/events/EVT-MISSING-999").expect(404);
    expect(res.body.error).toBe("Not Found");
    expect(res.body.message).toContain("EVT-MISSING-999");
  });

  it("GET /api/events -> should filter events by status and date range in Atlas", async () => {
    await request(app).post("/api/events").send({
      ...baseInput,
      eventName: "Filter Match Event",
      startTime: "2026-11-10T10:00:00Z",
      endTime: "2026-11-10T12:00:00Z",
    }).expect(201);

    await request(app).post("/api/events").send({
      ...baseInput,
      eventName: "Other Event",
      startTime: "2026-12-01T10:00:00Z",
      endTime: "2026-12-01T12:00:00Z",
    }).expect(201);

    const filterRes = await request(app)
      .get("/api/events?status=SCHEDULED&startDateFrom=2026-11-01T00:00:00Z&startDateTo=2026-11-15T00:00:00Z")
      .expect(200);

    expect(filterRes.body.events).toHaveLength(1);
    expect(filterRes.body.events[0].eventName).toBe("Filter Match Event");
  });

  it("GET /api/events -> should reject invalid query filter date range (startDateTo < startDateFrom) with 400 Bad Request", async () => {
    const res = await request(app)
      .get("/api/events?startDateFrom=2026-11-15T00:00:00Z&startDateTo=2026-11-01T00:00:00Z")
      .expect(400);

    expect(res.body.error).toBe("Bad Request");
    expect(res.body.message).toBe("Request validation failed");
    expect(res.body.issues.some((i: string) => i.includes("startDateTo must be later than or equal to startDateFrom"))).toBe(true);
  });

  it("GET /api/health & /api/health/ready -> should report healthy process and connected Atlas", async () => {
    const healthRes = await request(app).get("/api/health").expect(200);
    expect(healthRes.body.status).toBe("ok");

    const readyRes = await request(app).get("/api/health/ready").expect(200);
    expect(readyRes.body.status).toBe("ok");
    expect(readyRes.body.database).toBe("connected");
  });
});
