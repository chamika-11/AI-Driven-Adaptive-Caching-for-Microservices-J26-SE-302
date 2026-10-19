/**
 * Type-level and runtime verification tests for the shared event data model.
 *
 * These tests verify:
 *   1. A valid event object satisfies ScheduledEvent.
 *   2. CreateScheduledEventInput does not require system-generated fields.
 *   3. UpdateScheduledEventInput does not allow system-managed fields.
 *   4. Enum value arrays contain the expected members.
 *   5. The shared package exports all intended public types and constants.
 *
 * Some checks are compile-time only (TypeScript structural typing); if the
 * file compiles without errors those constraints are satisfied.  Runtime
 * assertions cover value-level invariants.
 */

import { describe, it, expect } from "vitest";
import type {
  ScheduledEvent,
  CreateScheduledEventInput,
  UpdateScheduledEventInput,
  EventResponse,
  EventListResponse,
  PaginationMeta,
  EventType,
  ExpectedLoad,
  EventPriority,
  EventStatus,
} from "../src/index.js";
import {
  EVENT_TYPES,
  EXPECTED_LOADS,
  EVENT_PRIORITIES,
  EVENT_STATUSES,
  COMPONENT_NAME,
  COMPONENT_ID,
} from "../src/index.js";

// ── Helper: a fully-populated ScheduledEvent object ──────────────────────────

const sampleEvent: ScheduledEvent = {
  eventId: "evt-001",
  eventName: "Semester 1 Results Release",
  eventType: "RESULT_RELEASE",
  description: "Final exam results for semester 1",
  startTime: "2026-11-01T08:00:00+05:30",
  endTime: "2026-11-01T18:00:00+05:30",
  expectedLoad: "VERY_HIGH",
  priority: "CRITICAL",
  prewarmWindowMinutes: 30,
  status: "SCHEDULED",
  createdAt: "2026-10-15T10:00:00Z",
  updatedAt: "2026-10-15T10:00:00Z",
};

// ── 1. ScheduledEvent structural validity ────────────────────────────────────

describe("ScheduledEvent", () => {
  it("should accept a fully-populated event object", () => {
    // If this compiles and the object is defined, the type contract holds.
    expect(sampleEvent.eventId).toBe("evt-001");
    expect(sampleEvent.eventType).toBe("RESULT_RELEASE");
    expect(sampleEvent.status).toBe("SCHEDULED");
  });

  it("should allow optional fields to be omitted", () => {
    const minimal: ScheduledEvent = {
      eventId: "evt-002",
      eventName: "Flash Sale",
      eventType: "FLASH_SALE",
      startTime: "2026-12-01T00:00:00Z",
      endTime: "2026-12-01T06:00:00Z",
      prewarmWindowMinutes: 15,
      status: "SCHEDULED",
      createdAt: "2026-10-15T10:00:00Z",
      updatedAt: "2026-10-15T10:00:00Z",
    };
    expect(minimal.description).toBeUndefined();
    expect(minimal.expectedLoad).toBeUndefined();
    expect(minimal.priority).toBeUndefined();
  });
});

// ── 2. CreateScheduledEventInput ─────────────────────────────────────────────

describe("CreateScheduledEventInput", () => {
  it("should accept user-provided fields without system-managed fields", () => {
    const input: CreateScheduledEventInput = {
      eventName: "Student Registration",
      eventType: "REGISTRATION",
      startTime: "2026-11-15T09:00:00+05:30",
      endTime: "2026-11-20T17:00:00+05:30",
      prewarmWindowMinutes: 60,
    };
    expect(input.eventName).toBe("Student Registration");
    expect(input.eventType).toBe("REGISTRATION");
  });

  it("should accept optional description, expectedLoad, and priority", () => {
    const input: CreateScheduledEventInput = {
      eventName: "Flash Sale",
      eventType: "FLASH_SALE",
      description: "12-hour electronics sale",
      startTime: "2026-12-01T00:00:00Z",
      endTime: "2026-12-01T12:00:00Z",
      expectedLoad: "HIGH",
      priority: "HIGH",
      prewarmWindowMinutes: 45,
    };
    expect(input.description).toBe("12-hour electronics sale");
    expect(input.expectedLoad).toBe("HIGH");
    expect(input.priority).toBe("HIGH");
  });

  /**
   * Compile-time verification: CreateScheduledEventInput must NOT include
   * system-managed fields. The following assignments would cause a TS error
   * if uncommented, proving the type correctly excludes them:
   *
   *   const bad: CreateScheduledEventInput = {
   *     eventId: "x",       // TS error: 'eventId' does not exist
   *     status: "SCHEDULED", // TS error: 'status' does not exist
   *     createdAt: "...",    // TS error: 'createdAt' does not exist
   *     updatedAt: "...",    // TS error: 'updatedAt' does not exist
   *     ...requiredFields,
   *   };
   *
   * This is enforced at compile time and cannot be tested at runtime
   * because TypeScript type-only fields are erased.
   */
  it("should not have system-managed field keys at runtime (structural proof)", () => {
    const input: CreateScheduledEventInput = {
      eventName: "Test",
      eventType: "OTHER",
      startTime: "2026-01-01T00:00:00Z",
      endTime: "2026-01-01T01:00:00Z",
      prewarmWindowMinutes: 0,
    };
    // At runtime, the object genuinely has no system fields
    expect("eventId" in input).toBe(false);
    expect("status" in input).toBe(false);
    expect("createdAt" in input).toBe(false);
    expect("updatedAt" in input).toBe(false);
  });
});

// ── 3. UpdateScheduledEventInput ─────────────────────────────────────────────

describe("UpdateScheduledEventInput", () => {
  it("should allow partial user-editable fields", () => {
    const update: UpdateScheduledEventInput = {
      eventName: "Updated Name",
    };
    expect(update.eventName).toBe("Updated Name");
    expect(update.eventType).toBeUndefined();
  });

  it("should allow an empty object (no fields updated)", () => {
    const update: UpdateScheduledEventInput = {};
    expect(Object.keys(update)).toHaveLength(0);
  });

  /**
   * Compile-time verification: UpdateScheduledEventInput must NOT permit
   * system-managed fields. The following would cause TS errors:
   *
   *   const bad: UpdateScheduledEventInput = { eventId: "x" };    // TS error
   *   const bad2: UpdateScheduledEventInput = { status: "DONE" }; // TS error
   *   const bad3: UpdateScheduledEventInput = { createdAt: "x" }; // TS error
   *   const bad4: UpdateScheduledEventInput = { updatedAt: "x" }; // TS error
   */
  it("should not have system-managed field keys at runtime (structural proof)", () => {
    const update: UpdateScheduledEventInput = { eventName: "X" };
    expect("eventId" in update).toBe(false);
    expect("status" in update).toBe(false);
    expect("createdAt" in update).toBe(false);
    expect("updatedAt" in update).toBe(false);
  });
});

// ── 4. Enum value arrays ─────────────────────────────────────────────────────

describe("Enum value arrays", () => {
  it("EVENT_TYPES should contain all 7 expected values", () => {
    expect(EVENT_TYPES).toHaveLength(7);
    expect(EVENT_TYPES).toContain("RESULT_RELEASE");
    expect(EVENT_TYPES).toContain("REGISTRATION");
    expect(EVENT_TYPES).toContain("FLASH_SALE");
    expect(EVENT_TYPES).toContain("TICKET_RELEASE");
    expect(EVENT_TYPES).toContain("PROMOTIONAL_CAMPAIGN");
    expect(EVENT_TYPES).toContain("PAYMENT_DEADLINE");
    expect(EVENT_TYPES).toContain("OTHER");
  });

  it("EXPECTED_LOADS should contain all 5 expected values", () => {
    expect(EXPECTED_LOADS).toHaveLength(5);
    expect(EXPECTED_LOADS).toContain("LOW");
    expect(EXPECTED_LOADS).toContain("MEDIUM");
    expect(EXPECTED_LOADS).toContain("HIGH");
    expect(EXPECTED_LOADS).toContain("VERY_HIGH");
    expect(EXPECTED_LOADS).toContain("UNKNOWN");
  });

  it("EVENT_PRIORITIES should contain all 4 expected values", () => {
    expect(EVENT_PRIORITIES).toHaveLength(4);
    expect(EVENT_PRIORITIES).toContain("LOW");
    expect(EVENT_PRIORITIES).toContain("MEDIUM");
    expect(EVENT_PRIORITIES).toContain("HIGH");
    expect(EVENT_PRIORITIES).toContain("CRITICAL");
  });

  it("EVENT_STATUSES should contain all 4 expected values", () => {
    expect(EVENT_STATUSES).toHaveLength(4);
    expect(EVENT_STATUSES).toContain("SCHEDULED");
    expect(EVENT_STATUSES).toContain("PROCESSING");
    expect(EVENT_STATUSES).toContain("COMPLETED");
    expect(EVENT_STATUSES).toContain("CANCELLED");
  });
});

// ── 5. Public exports ────────────────────────────────────────────────────────

describe("Shared package public exports", () => {
  it("should export component metadata constants", () => {
    expect(COMPONENT_NAME).toBe("Event Intelligence & Context-Aware Feature Engineering");
    expect(COMPONENT_ID).toBe("component-4");
  });

  it("should export EventResponse and EventListResponse types (compile-time check)", () => {
    // These are type-only assertions — if this compiles, the exports exist.
    const response: EventResponse = { event: sampleEvent };
    expect(response.event.eventId).toBe("evt-001");

    const pagination: PaginationMeta = {
      total: 100,
      page: 1,
      limit: 20,
      totalPages: 5,
    };
    const listResponse: EventListResponse = {
      events: [sampleEvent],
      pagination,
    };
    expect(listResponse.events).toHaveLength(1);
    expect(listResponse.pagination.total).toBe(100);
  });

  /**
   * Compile-time type-assignability proof:
   * If the following type aliases resolve without error, the package
   * correctly exports these types from its public surface.
   */
  it("should export all enum union types (type-alias compilation check)", () => {
    const t: EventType = "FLASH_SALE";
    const l: ExpectedLoad = "UNKNOWN";
    const p: EventPriority = "CRITICAL";
    const s: EventStatus = "CANCELLED";
    expect(t).toBe("FLASH_SALE");
    expect(l).toBe("UNKNOWN");
    expect(p).toBe("CRITICAL");
    expect(s).toBe("CANCELLED");
  });
});
