/**
 * Unit tests for Mongoose ScheduledEvent Model (Part 2.2).
 *
 * Verifies:
 *   1. Model import does not initiate a database connection.
 *   2. Valid event documents satisfy Mongoose schema validation without a live DB.
 *   3. Required field constraints are strictly enforced.
 *   4. Enum value constraints match canonical shared types.
 *   5. Prewarm window boundary and integer rules.
 *   6. Cross-field temporal validation (endTime > startTime).
 *   7. Whitespace trimming and maximum length limits.
 *   8. Schema index specifications (eventId unique index, compound status + startTime index).
 *   9. Contract mapping boundary: toScheduledEvent() converts BSON dates to ISO strings,
 *      omits internal _id/__v, and satisfies ScheduledEventSchema.
 *  10. Compatibility with shared sample fixtures.
 */

import { describe, it, expect } from "vitest";
import mongoose from "mongoose";
import {
  ScheduledEventModel,
  scheduledEventSchema,
  mapDocumentToScheduledEvent,
} from "../src/models/index.js";
import {
  ScheduledEventSchema,
  SAMPLE_SCHEDULED_EVENTS,
  EVENT_NAME_MAX_LENGTH,
  DESCRIPTION_MAX_LENGTH,
  PREWARM_WINDOW_MAX_MINUTES,
} from "@component4/shared";

describe("Part 2.2: Mongoose ScheduledEvent Model", () => {
  const validEventData = {
    eventId: "EVT-TEST-001",
    eventName: "Semester 1 Exam Results Release",
    eventType: "RESULT_RELEASE" as const,
    description: "Official results announcement on portal",
    startTime: new Date("2026-11-15T08:00:00.000Z"),
    endTime: new Date("2026-11-15T18:00:00.000Z"),
    expectedLoad: "VERY_HIGH" as const,
    priority: "CRITICAL" as const,
    prewarmWindowMinutes: 60,
    status: "SCHEDULED" as const,
  };

  // ── 1. Import Safety ────────────────────────────────────────────────────────

  describe("1. Connection Isolation", () => {
    it("importing the model must not initiate a connection to MongoDB Atlas", () => {
      // In unit test environment, readyState must remain 0 (disconnected)
      expect(mongoose.connection.readyState).toBe(0);
    });
  });

  // ── 2. Valid Document Validation ────────────────────────────────────────────

  describe("2. Valid Document Validation", () => {
    it("should validate a complete valid event document", async () => {
      const doc = new ScheduledEventModel(validEventData);
      const validationError = doc.validateSync();
      expect(validationError).toBeUndefined();
    });

    it("should allow omitting optional fields (description, expectedLoad, priority)", async () => {
      const minimalData = {
        eventId: "EVT-TEST-002",
        eventName: "Minimal Event",
        eventType: "FLASH_SALE" as const,
        startTime: new Date("2026-12-01T10:00:00.000Z"),
        endTime: new Date("2026-12-01T12:00:00.000Z"),
        prewarmWindowMinutes: 15,
      };

      const doc = new ScheduledEventModel(minimalData);
      const err = doc.validateSync();
      expect(err).toBeUndefined();
      expect(doc.status).toBe("SCHEDULED"); // Schema default
      expect(doc.description).toBeUndefined();
      expect(doc.expectedLoad).toBeUndefined();
      expect(doc.priority).toBeUndefined();
    });
  });

  // ── 3. Required Fields Enforcement ──────────────────────────────────────────

  describe("3. Required Fields Enforcement", () => {
    it.each([
      ["eventId", "eventId is required"],
      ["eventName", "eventName is required"],
      ["eventType", "eventType is required"],
      ["startTime", "startTime is required"],
      ["endTime", "endTime is required"],
      ["prewarmWindowMinutes", "prewarmWindowMinutes is required"],
    ])("should require field %s", (field, expectedMessage) => {
      const data = { ...validEventData };
      delete (data as Record<string, unknown>)[field];

      const doc = new ScheduledEventModel(data);
      const err = doc.validateSync();

      expect(err).toBeDefined();
      expect(err?.errors[field]).toBeDefined();
      expect(err?.errors[field]?.message).toContain(expectedMessage);
    });
  });

  // ── 4. Enum Constraints ─────────────────────────────────────────────────────

  describe("4. Enum Constraints", () => {
    it("should reject invalid eventType", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        eventType: "UNRECOGNIZED_TYPE",
      });
      const err = doc.validateSync();
      expect(err?.errors["eventType"]).toBeDefined();
      expect(err?.errors["eventType"]?.message).toContain("Invalid eventType");
    });

    it("should reject invalid expectedLoad", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        expectedLoad: "EXTREME_LOAD",
      });
      const err = doc.validateSync();
      expect(err?.errors["expectedLoad"]).toBeDefined();
      expect(err?.errors["expectedLoad"]?.message).toContain("Invalid expectedLoad");
    });

    it("should reject invalid priority", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        priority: "URGENT",
      });
      const err = doc.validateSync();
      expect(err?.errors["priority"]).toBeDefined();
      expect(err?.errors["priority"]?.message).toContain("Invalid priority");
    });

    it("should reject invalid status", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        status: "DELETED",
      });
      const err = doc.validateSync();
      expect(err?.errors["status"]).toBeDefined();
      expect(err?.errors["status"]?.message).toContain("Invalid status");
    });
  });

  // ── 5. Prewarm Window Constraints ───────────────────────────────────────────

  describe("5. Prewarm Window Invariants", () => {
    it("should reject negative prewarmWindowMinutes", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        prewarmWindowMinutes: -5,
      });
      const err = doc.validateSync();
      expect(err?.errors["prewarmWindowMinutes"]).toBeDefined();
      expect(err?.errors["prewarmWindowMinutes"]?.message).toContain("prewarmWindowMinutes must be an integer");
    });

    it("should reject fractional prewarmWindowMinutes", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        prewarmWindowMinutes: 15.5,
      });
      const err = doc.validateSync();
      expect(err?.errors["prewarmWindowMinutes"]).toBeDefined();
    });

    it("should reject prewarmWindowMinutes exceeding maximum allowable limit", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        prewarmWindowMinutes: PREWARM_WINDOW_MAX_MINUTES + 1,
      });
      const err = doc.validateSync();
      expect(err?.errors["prewarmWindowMinutes"]).toBeDefined();
    });

    it("should accept lower boundary (0) and upper boundary (10080)", () => {
      const docMin = new ScheduledEventModel({
        ...validEventData,
        prewarmWindowMinutes: 0,
      });
      expect(docMin.validateSync()).toBeUndefined();

      const docMax = new ScheduledEventModel({
        ...validEventData,
        prewarmWindowMinutes: PREWARM_WINDOW_MAX_MINUTES,
      });
      expect(docMax.validateSync()).toBeUndefined();
    });
  });

  // ── 6. Cross-Field Temporal Validation ──────────────────────────────────────

  describe("6. Cross-Field Temporal Validation (endTime > startTime)", () => {
    it("should reject when endTime is equal to startTime", () => {
      const date = new Date("2026-11-15T10:00:00.000Z");
      const doc = new ScheduledEventModel({
        ...validEventData,
        startTime: date,
        endTime: date,
      });
      const err = doc.validateSync();
      expect(err?.errors["endTime"]).toBeDefined();
      expect(err?.errors["endTime"]?.message).toContain("endTime must be strictly later than startTime");
    });

    it("should reject when endTime is earlier than startTime", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        startTime: new Date("2026-11-15T18:00:00.000Z"),
        endTime: new Date("2026-11-15T08:00:00.000Z"),
      });
      const err = doc.validateSync();
      expect(err?.errors["endTime"]).toBeDefined();
      expect(err?.errors["endTime"]?.message).toContain("endTime must be strictly later than startTime");
    });

    it("should pass when endTime is later than startTime", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        startTime: new Date("2026-11-15T08:00:00.000Z"),
        endTime: new Date("2026-11-15T08:00:01.000Z"), // 1 second later
      });
      expect(doc.validateSync()).toBeUndefined();
    });
  });

  // ── 7. Trimming and Length Limits ───────────────────────────────────────────

  describe("7. Trimming and String Constraints", () => {
    it("should trim eventName and eventId whitespace", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        eventId: "  EVT-TRIMMED-001  ",
        eventName: "   Untrimmed Title   ",
      });

      expect(doc.eventId).toBe("EVT-TRIMMED-001");
      expect(doc.eventName).toBe("Untrimmed Title");
    });

    it("should reject eventName exceeding maximum length", () => {
      const longName = "A".repeat(EVENT_NAME_MAX_LENGTH + 1);
      const doc = new ScheduledEventModel({
        ...validEventData,
        eventName: longName,
      });
      const err = doc.validateSync();
      expect(err?.errors["eventName"]).toBeDefined();
    });

    it("should reject description exceeding maximum length", () => {
      const longDesc = "D".repeat(DESCRIPTION_MAX_LENGTH + 1);
      const doc = new ScheduledEventModel({
        ...validEventData,
        description: longDesc,
      });
      const err = doc.validateSync();
      expect(err?.errors["description"]).toBeDefined();
    });
  });

  // ── 8. Schema Indexes ───────────────────────────────────────────────────────

  describe("8. Schema Index Specifications", () => {
    it("should declare eventId as unique index in schema definition", () => {
      // In Mongoose schema, eventId is declared with { unique: true }
      const eventIdPath = scheduledEventSchema.path("eventId") as unknown as {
        _index?: { unique?: boolean };
      };
      expect(eventIdPath._index?.unique).toBe(true);
    });

    it("should declare compound index for scheduler queries ({ status: 1, startTime: 1 })", () => {
      const indexes = scheduledEventSchema.indexes();
      const compoundIndex = indexes.find((idx) => {
        const fields = idx[0];
        return fields["status"] === 1 && fields["startTime"] === 1;
      });

      expect(compoundIndex).toBeDefined();
    });

    it("should have exactly one unique index on eventId without duplicate registrations", () => {
      const indexes = scheduledEventSchema.indexes();
      const eventIdIndexes = indexes.filter((idx) => {
        const fields = idx[0];
        return Object.keys(fields).length === 1 && fields["eventId"] === 1;
      });
      // Exactly 1 unique index definition on eventId
      expect(eventIdIndexes.length).toBe(1);
      expect(eventIdIndexes[0][1]?.unique).toBe(true);
    });
  });

  // ── 9. Contract Mapping Boundary ────────────────────────────────────────────

  describe("9. Contract Mapping Boundary", () => {
    it("toScheduledEvent() should serialize BSON Dates to ISO strings and omit _id / __v", () => {
      const doc = new ScheduledEventModel({
        ...validEventData,
        createdAt: new Date("2026-10-01T09:00:00.000Z"),
        updatedAt: new Date("2026-10-01T09:00:00.000Z"),
      });

      const apiEvent = doc.toScheduledEvent();

      // Check fields
      expect(apiEvent.eventId).toBe("EVT-TEST-001");
      expect(apiEvent.eventName).toBe("Semester 1 Exam Results Release");
      expect(apiEvent.eventType).toBe("RESULT_RELEASE");
      expect(apiEvent.startTime).toBe("2026-11-15T08:00:00.000Z");
      expect(apiEvent.endTime).toBe("2026-11-15T18:00:00.000Z");
      expect(apiEvent.status).toBe("SCHEDULED");
      expect(apiEvent.createdAt).toBe("2026-10-01T09:00:00.000Z");
      expect(apiEvent.updatedAt).toBe("2026-10-01T09:00:00.000Z");

      // Verify internal Mongoose fields are NOT exposed
      const record = apiEvent as Record<string, unknown>;
      expect(record["_id"]).toBeUndefined();
      expect(record["__v"]).toBeUndefined();

      // Verify that mapped output passes the strict shared Zod schema
      const zodResult = ScheduledEventSchema.safeParse(apiEvent);
      expect(zodResult.success).toBe(true);
    });

    it("mapDocumentToScheduledEvent standalone function works with plain objects", () => {
      const mapped = mapDocumentToScheduledEvent({
        _id: "mongo-internal-id",
        __v: 0,
        eventId: "EVT-TEST-003",
        eventName: "Standalone Map Event",
        eventType: "OTHER",
        startTime: new Date("2026-11-01T10:00:00.000Z"),
        endTime: new Date("2026-11-01T12:00:00.000Z"),
        prewarmWindowMinutes: 10,
        status: "PROCESSING",
        createdAt: new Date("2026-10-15T00:00:00.000Z"),
        updatedAt: new Date("2026-10-15T00:00:00.000Z"),
      });

      expect(mapped.eventId).toBe("EVT-TEST-003");
      expect(mapped.status).toBe("PROCESSING");
      expect((mapped as Record<string, unknown>)["_id"]).toBeUndefined();
      expect(ScheduledEventSchema.safeParse(mapped).success).toBe(true);
    });
  });

  // ── 10. Sample Fixtures Compatibility ───────────────────────────────────────

  describe("10. Shared Sample Fixtures Compatibility", () => {
    it.each(SAMPLE_SCHEDULED_EVENTS.map((f) => [f.eventId, f.eventName, f]))(
      "should load and validate shared fixture %s (%s)",
      (_, __, fixture) => {
        const doc = new ScheduledEventModel({
          eventId: fixture.eventId,
          eventName: fixture.eventName,
          eventType: fixture.eventType,
          description: fixture.description,
          startTime: new Date(fixture.startTime),
          endTime: new Date(fixture.endTime),
          expectedLoad: fixture.expectedLoad,
          priority: fixture.priority,
          prewarmWindowMinutes: fixture.prewarmWindowMinutes,
          status: fixture.status,
          createdAt: new Date(fixture.createdAt),
          updatedAt: new Date(fixture.updatedAt),
        });

        const err = doc.validateSync();
        expect(err).toBeUndefined();

        const roundTripped = doc.toScheduledEvent();
        expect(roundTripped.eventId).toBe(fixture.eventId);
        expect(ScheduledEventSchema.safeParse(roundTripped).success).toBe(true);
      }
    );
  });
});
