/**
 * Comprehensive verification tests for Sample Event Fixtures (Part 1.4).
 *
 * Verifies:
 *   1. Every complete valid event satisfies ScheduledEventSchema.
 *   2. Every valid create fixture satisfies CreateScheduledEventInputSchema.
 *   3. All fixture event IDs are unique and deterministic.
 *   4. All event start and end times satisfy ISO 8601 with explicit timezone.
 *   5. All event end times are later than start times.
 *   6. Prewarm windows satisfy schema limits (non-negative integer <= 10080).
 *   7. Enum values conform to canonical shared constants (EVENT_TYPES, EXPECTED_LOADS, etc.).
 *   8. All intentionally invalid test cases fail validation on their target schemas.
 *   9. Fixtures and collections are correctly exported through @component4/shared.
 *  10. Full compatibility and isolation from system runtime logic.
 */

import { describe, it, expect } from "vitest";
import {
  ScheduledEventSchema,
  CreateScheduledEventInputSchema,
  UpdateScheduledEventInputSchema,
  EVENT_TYPES,
  EXPECTED_LOADS,
  EVENT_PRIORITIES,
  EVENT_STATUSES,
  PREWARM_WINDOW_MIN_MINUTES,
  PREWARM_WINDOW_MAX_MINUTES,
  SAMPLE_SCHEDULED_EVENTS,
  SAMPLE_CREATE_EVENT_INPUTS,
  INVALID_FIXTURES,
  FIXTURE_RESULT_RELEASE,
  FIXTURE_REGISTRATION_OPENING,
  FIXTURE_FLASH_SALE,
  FIXTURE_TICKET_RELEASE,
  FIXTURE_PROMOTIONAL_CAMPAIGN,
  FIXTURE_PAYMENT_DEADLINE,
  FIXTURE_LOW_DEMAND_EVENT,
  FIXTURE_COMPLETED_EVENT,
  FIXTURE_CANCELLED_EVENT,
  FIXTURE_PROCESSING_EVENT,
  CREATE_FIXTURE_MINIMAL,
  CREATE_FIXTURE_WITH_OPTIONAL,
  CREATE_FIXTURE_RESULT_RELEASE,
  CREATE_FIXTURE_REGISTRATION_ALT_PREWARM,
} from "../src/index.js";

describe("Part 1.4: Sample Event Fixtures Verification", () => {
  // ── 1. Complete ScheduledEvent Fixture Validation ──────────────────────────

  describe("1. Complete ScheduledEvent Validation (ScheduledEventSchema)", () => {
    it.each(SAMPLE_SCHEDULED_EVENTS.map((e) => [e.eventId, e.eventName, e]))(
      "should validate fixture %s (%s)",
      (eventId, _, event) => {
        const result = ScheduledEventSchema.safeParse(event);
        if (!result.success) {
          throw new Error(
            `Fixture ${eventId} failed ScheduledEventSchema validation: ${JSON.stringify(result.error.issues, null, 2)}`
          );
        }
        expect(result.success).toBe(true);
        expect(result.data.eventId).toBe(eventId);
      }
    );

    it("should have at least 8 distinct event fixtures covering required scenarios", () => {
      expect(SAMPLE_SCHEDULED_EVENTS.length).toBeGreaterThanOrEqual(8);
    });

    it("should cover required business scenarios", () => {
      const types = new Set(SAMPLE_SCHEDULED_EVENTS.map((e) => e.eventType));
      expect(types.has("RESULT_RELEASE")).toBe(true);
      expect(types.has("REGISTRATION")).toBe(true);
      expect(types.has("FLASH_SALE")).toBe(true);
      expect(types.has("TICKET_RELEASE")).toBe(true);
      expect(types.has("PROMOTIONAL_CAMPAIGN")).toBe(true);
      expect(types.has("PAYMENT_DEADLINE")).toBe(true);
      expect(types.has("OTHER")).toBe(true);
    });

    it("should cover all lifecycle states: SCHEDULED, PROCESSING, COMPLETED, CANCELLED", () => {
      const statuses = new Set(SAMPLE_SCHEDULED_EVENTS.map((e) => e.status));
      expect(statuses.has("SCHEDULED")).toBe(true);
      expect(statuses.has("PROCESSING")).toBe(true);
      expect(statuses.has("COMPLETED")).toBe(true);
      expect(statuses.has("CANCELLED")).toBe(true);
    });

    it("should cover a diverse distribution of expected load levels", () => {
      const loads = new Set(
        SAMPLE_SCHEDULED_EVENTS.map((e) => e.expectedLoad).filter(Boolean)
      );
      expect(loads.has("LOW")).toBe(true);
      expect(loads.has("MEDIUM")).toBe(true);
      expect(loads.has("HIGH")).toBe(true);
      expect(loads.has("VERY_HIGH")).toBe(true);
      expect(loads.has("UNKNOWN")).toBe(true);
    });

    it("should cover all priority levels", () => {
      const priorities = new Set(
        SAMPLE_SCHEDULED_EVENTS.map((e) => e.priority).filter(Boolean)
      );
      expect(priorities.has("LOW")).toBe(true);
      expect(priorities.has("MEDIUM")).toBe(true);
      expect(priorities.has("HIGH")).toBe(true);
      expect(priorities.has("CRITICAL")).toBe(true);
    });
  });

  // ── 2. Create-Input Fixture Validation ──────────────────────────────────────

  describe("2. Create-Input Fixtures Validation (CreateScheduledEventInputSchema)", () => {
    it.each(SAMPLE_CREATE_EVENT_INPUTS.map((c, i) => [i + 1, c.eventName, c]))(
      "should validate create payload #%i (%s)",
      (index, _, payload) => {
        const result = CreateScheduledEventInputSchema.safeParse(payload);
        if (!result.success) {
          throw new Error(
            `Create fixture #${index} failed CreateScheduledEventInputSchema validation: ${JSON.stringify(result.error.issues, null, 2)}`
          );
        }
        expect(result.success).toBe(true);
      }
    );

    it("minimal create payload should exclude optional fields", () => {
      expect(CREATE_FIXTURE_MINIMAL.description).toBeUndefined();
      expect(CREATE_FIXTURE_MINIMAL.expectedLoad).toBeUndefined();
      expect(CREATE_FIXTURE_MINIMAL.priority).toBeUndefined();
    });

    it("all create fixtures must NOT contain system-managed fields", () => {
      SAMPLE_CREATE_EVENT_INPUTS.forEach((fixture, idx) => {
        const record = fixture as Record<string, unknown>;
        expect("eventId" in record, `create fixture #${idx + 1} has eventId`).toBe(false);
        expect("status" in record, `create fixture #${idx + 1} has status`).toBe(false);
        expect("createdAt" in record, `create fixture #${idx + 1} has createdAt`).toBe(false);
        expect("updatedAt" in record, `create fixture #${idx + 1} has updatedAt`).toBe(false);
      });
    });
  });

  // ── 3. Unique, Deterministic Identifiers ────────────────────────────────────

  describe("3. Unique and Deterministic Identifiers", () => {
    it("all fixture event IDs must be unique", () => {
      const ids = SAMPLE_SCHEDULED_EVENTS.map((e) => e.eventId);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(ids.length);
    });

    it("all fixture event IDs must match the EVT-FIXTURE-XXX naming standard", () => {
      const idPattern = /^EVT-FIXTURE-\d{3}$/;
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        expect(e.eventId).toMatch(idPattern);
      });
    });
  });

  // ── 4 & 5. Datetime Invariants ─────────────────────────────────────────────

  describe("4 & 5. Datetimes and Cross-Field Temporal Invariants", () => {
    it("all event start and end times must have an explicit timezone", () => {
      const tzPattern = /(Z|[+-]\d{2}:\d{2})$/;
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        expect(e.startTime).toMatch(tzPattern);
        expect(e.endTime).toMatch(tzPattern);
        expect(e.createdAt).toMatch(tzPattern);
        expect(e.updatedAt).toMatch(tzPattern);
      });
    });

    it("every event endTime must be strictly after startTime", () => {
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        const startMillis = new Date(e.startTime).getTime();
        const endMillis = new Date(e.endTime).getTime();
        expect(endMillis).toBeGreaterThan(startMillis);
      });
    });

    it("every create fixture endTime must be strictly after startTime", () => {
      SAMPLE_CREATE_EVENT_INPUTS.forEach((c) => {
        const startMillis = new Date(c.startTime).getTime();
        const endMillis = new Date(c.endTime).getTime();
        expect(endMillis).toBeGreaterThan(startMillis);
      });
    });
  });

  // ── 6. Prewarm Window Bounds ───────────────────────────────────────────────

  describe("6. Prewarm Window Constraints", () => {
    it("all prewarmWindowMinutes values must be non-negative integers within bounds", () => {
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        expect(Number.isInteger(e.prewarmWindowMinutes)).toBe(true);
        expect(e.prewarmWindowMinutes).toBeGreaterThanOrEqual(PREWARM_WINDOW_MIN_MINUTES);
        expect(e.prewarmWindowMinutes).toBeLessThanOrEqual(PREWARM_WINDOW_MAX_MINUTES);
      });

      SAMPLE_CREATE_EVENT_INPUTS.forEach((c) => {
        expect(Number.isInteger(c.prewarmWindowMinutes)).toBe(true);
        expect(c.prewarmWindowMinutes).toBeGreaterThanOrEqual(PREWARM_WINDOW_MIN_MINUTES);
        expect(c.prewarmWindowMinutes).toBeLessThanOrEqual(PREWARM_WINDOW_MAX_MINUTES);
      });
    });

    it("includes diverse realistic prewarm windows (e.g. 5, 15, 30, 45, 60, 120)", () => {
      const windows = new Set([
        ...SAMPLE_SCHEDULED_EVENTS.map((e) => e.prewarmWindowMinutes),
        ...SAMPLE_CREATE_EVENT_INPUTS.map((c) => c.prewarmWindowMinutes),
      ]);
      expect(windows.has(5)).toBe(true);
      expect(windows.has(15)).toBe(true);
      expect(windows.has(30)).toBe(true);
      expect(windows.has(45)).toBe(true);
      expect(windows.has(60)).toBe(true);
      expect(windows.has(120)).toBe(true);
    });
  });

  // ── 7. Enum Value Conformance ──────────────────────────────────────────────

  describe("7. Enum Conformance to Part 1.2 Contracts", () => {
    it("all event types must exist in EVENT_TYPES", () => {
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        expect(EVENT_TYPES).toContain(e.eventType);
      });
    });

    it("all expected load values must exist in EXPECTED_LOADS", () => {
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        if (e.expectedLoad) {
          expect(EXPECTED_LOADS).toContain(e.expectedLoad);
        }
      });
    });

    it("all priority values must exist in EVENT_PRIORITIES", () => {
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        if (e.priority) {
          expect(EVENT_PRIORITIES).toContain(e.priority);
        }
      });
    });

    it("all status values must exist in EVENT_STATUSES", () => {
      SAMPLE_SCHEDULED_EVENTS.forEach((e) => {
        expect(EVENT_STATUSES).toContain(e.status);
      });
    });
  });

  // ── 8. Invalid Test Cases Rejection ────────────────────────────────────────

  describe("8. Intentionally Invalid Test Cases Rejection", () => {
    it.each(INVALID_FIXTURES.map((tc) => [tc.caseId, tc.scenario, tc]))(
      "should reject invalid fixture %s: %s",
      (caseId, _, tc) => {
        let result;
        if (tc.targetSchema === "CreateScheduledEventInputSchema") {
          result = CreateScheduledEventInputSchema.safeParse(tc.payload);
        } else if (tc.targetSchema === "UpdateScheduledEventInputSchema") {
          result = UpdateScheduledEventInputSchema.safeParse(tc.payload);
        } else {
          result = ScheduledEventSchema.safeParse(tc.payload);
        }

        expect(result.success, `Expected fixture ${caseId} to fail validation`).toBe(false);

        if (!result.success) {
          if (tc.expectedIssueField) {
            const fields = result.error.issues.map((i) => i.path.join("."));
            expect(fields).toContain(tc.expectedIssueField);
          }
          if (tc.expectedIssueCode) {
            const codes = result.error.issues.map((i) => i.code);
            expect(codes).toContain(tc.expectedIssueCode);
          }
        }
      }
    );

    it("invalid fixtures must be strictly isolated from valid collections", () => {
      const validIds = new Set(SAMPLE_SCHEDULED_EVENTS.map((e) => e.eventId));
      INVALID_FIXTURES.forEach((inv) => {
        const payloadRecord = inv.payload as Record<string, unknown>;
        if (payloadRecord && typeof payloadRecord.eventId === "string") {
          expect(validIds.has(payloadRecord.eventId)).toBe(false);
        }
      });
    });
  });

  // ── 9. Package Public Entry Point Exports ───────────────────────────────────

  describe("9. Shared Package Exports", () => {
    it("should export all individual complete event fixtures", () => {
      expect(FIXTURE_RESULT_RELEASE.eventId).toBe("EVT-FIXTURE-001");
      expect(FIXTURE_REGISTRATION_OPENING.eventId).toBe("EVT-FIXTURE-002");
      expect(FIXTURE_FLASH_SALE.eventId).toBe("EVT-FIXTURE-003");
      expect(FIXTURE_TICKET_RELEASE.eventId).toBe("EVT-FIXTURE-004");
      expect(FIXTURE_PROMOTIONAL_CAMPAIGN.eventId).toBe("EVT-FIXTURE-005");
      expect(FIXTURE_PAYMENT_DEADLINE.eventId).toBe("EVT-FIXTURE-006");
      expect(FIXTURE_LOW_DEMAND_EVENT.eventId).toBe("EVT-FIXTURE-007");
      expect(FIXTURE_COMPLETED_EVENT.eventId).toBe("EVT-FIXTURE-008");
      expect(FIXTURE_CANCELLED_EVENT.eventId).toBe("EVT-FIXTURE-009");
      expect(FIXTURE_PROCESSING_EVENT.eventId).toBe("EVT-FIXTURE-010");
    });

    it("should export individual create-input fixtures", () => {
      expect(CREATE_FIXTURE_MINIMAL.eventName).toBeDefined();
      expect(CREATE_FIXTURE_WITH_OPTIONAL.expectedLoad).toBe("MEDIUM");
      expect(CREATE_FIXTURE_RESULT_RELEASE.priority).toBe("CRITICAL");
      expect(CREATE_FIXTURE_REGISTRATION_ALT_PREWARM.prewarmWindowMinutes).toBe(120);
    });

    it("should export collections", () => {
      expect(Array.isArray(SAMPLE_SCHEDULED_EVENTS)).toBe(true);
      expect(Array.isArray(SAMPLE_CREATE_EVENT_INPUTS)).toBe(true);
      expect(Array.isArray(INVALID_FIXTURES)).toBe(true);
    });
  });
});
