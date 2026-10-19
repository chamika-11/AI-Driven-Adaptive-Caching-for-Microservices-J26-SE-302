/**
 * Comprehensive runtime validation tests for Part 1.3 Zod schemas.
 *
 * Covers:
 *   1. Enum Schemas: valid values, invalid values, descriptive error messages.
 *   2. Datetime Validation: ISO 8601 with mandatory timezone, leap years,
 *      invalid calendar dates, offset bounds, string preservation.
 *   3. ScheduledEventSchema: complete entity, optional fields, limits,
 *      cross-field rules, historical dates.
 *   4. CreateScheduledEventInputSchema: required only, optional fields, strict rejection
 *      of system-managed fields and unknown properties.
 *   5. UpdateScheduledEventInputSchema: partial updates, empty rejection,
 *      cross-field date rules, single-date service-layer documentation.
 *   6. Response Schemas: EventResponse, EventListResponse, and PaginationMeta
 *      mathematical consistency.
 *   7. Security & Error Formatting: clean issue reporting without sensitive leakage.
 */

import { describe, it, expect } from "vitest";
import {
  EventTypeSchema,
  ExpectedLoadSchema,
  EventPrioritySchema,
  EventStatusSchema,
  IsoDatetimeStringSchema,
  ScheduledEventSchema,
  CreateScheduledEventInputSchema,
  UpdateScheduledEventInputSchema,
  PaginationMetaSchema,
  EventResponseSchema,
  EventListResponseSchema,
  EVENT_NAME_MIN_LENGTH,
  EVENT_NAME_MAX_LENGTH,
  DESCRIPTION_MAX_LENGTH,
  PREWARM_WINDOW_MIN_MINUTES,
  PREWARM_WINDOW_MAX_MINUTES,
  PAGINATION_PAGE_MIN,
  PAGINATION_LIMIT_MIN,
  PAGINATION_LIMIT_MAX,
} from "../src/index.js";
import {
  EVENT_TYPES,
  EXPECTED_LOADS,
  EVENT_PRIORITIES,
  EVENT_STATUSES,
} from "../src/index.js";

// ── Fixture: canonical valid ScheduledEvent ───────────────────────────────────

const validScheduledEvent = {
  eventId: "evt-uuid-12345",
  eventName: "Annual Student Registration",
  eventType: "REGISTRATION",
  description: "Annual academic registration window for all faculties",
  startTime: "2026-11-01T08:00:00+05:30",
  endTime: "2026-11-01T18:00:00+05:30",
  expectedLoad: "HIGH",
  priority: "HIGH",
  prewarmWindowMinutes: 60,
  status: "SCHEDULED",
  createdAt: "2026-10-15T10:00:00Z",
  updatedAt: "2026-10-15T10:00:00Z",
};

// ── 1. Enum Schemas ──────────────────────────────────────────────────────────

describe("5.1 Enum Schemas", () => {
  describe("EventTypeSchema", () => {
    it.each(EVENT_TYPES)("should accept valid EventType: %s", (type) => {
      const result = EventTypeSchema.safeParse(type);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toBe(type);
      }
    });

    it.each(["INVALID_TYPE", "flash_sale", "", "other", "UNKNOWN"])(
      "should reject invalid EventType: %s",
      (invalid) => {
        const result = EventTypeSchema.safeParse(invalid);
        expect(result.success).toBe(false);
        if (!result.success) {
          expect(result.error.issues[0].message).toContain("Invalid eventType");
        }
      }
    );

    it("should reject non-string types", () => {
      expect(EventTypeSchema.safeParse(123).success).toBe(false);
      expect(EventTypeSchema.safeParse(null).success).toBe(false);
      expect(EventTypeSchema.safeParse(undefined).success).toBe(false);
    });
  });

  describe("ExpectedLoadSchema", () => {
    it.each(EXPECTED_LOADS)("should accept valid ExpectedLoad: %s", (load) => {
      const result = ExpectedLoadSchema.safeParse(load);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toBe(load);
      }
    });

    it.each(["EXTREME", "low", "NORMAL", ""])(
      "should reject invalid ExpectedLoad: %s",
      (invalid) => {
        const result = ExpectedLoadSchema.safeParse(invalid);
        expect(result.success).toBe(false);
        if (!result.success) {
          expect(result.error.issues[0].message).toContain("Invalid expectedLoad");
        }
      }
    );
  });

  describe("EventPrioritySchema", () => {
    it.each(EVENT_PRIORITIES)("should accept valid EventPriority: %s", (priority) => {
      const result = EventPrioritySchema.safeParse(priority);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toBe(priority);
      }
    });

    it.each(["URGENT", "high", "NONE", ""])(
      "should reject invalid EventPriority: %s",
      (invalid) => {
        const result = EventPrioritySchema.safeParse(invalid);
        expect(result.success).toBe(false);
        if (!result.success) {
          expect(result.error.issues[0].message).toContain("Invalid priority");
        }
      }
    );
  });

  describe("EventStatusSchema", () => {
    it.each(EVENT_STATUSES)("should accept valid EventStatus: %s", (status) => {
      const result = EventStatusSchema.safeParse(status);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toBe(status);
      }
    });

    it.each(["PENDING", "ACTIVE", "scheduled", ""])(
      "should reject invalid EventStatus: %s",
      (invalid) => {
        const result = EventStatusSchema.safeParse(invalid);
        expect(result.success).toBe(false);
        if (!result.success) {
          expect(result.error.issues[0].message).toContain("Invalid status");
        }
      }
    );
  });
});

// ── 2. Datetime Validation ───────────────────────────────────────────────────

describe("5.2 Datetime Validation (IsoDatetimeStringSchema)", () => {
  describe("Valid datetime strings", () => {
    const validDatetimes = [
      ["UTC 'Z' format", "2026-11-01T08:00:00Z"],
      ["Positive UTC offset (+05:30)", "2026-11-01T08:00:00+05:30"],
      ["Negative UTC offset (-08:00)", "2026-11-01T08:00:00-08:00"],
      ["Explicit positive zero offset (+00:00)", "2026-11-01T08:00:00+00:00"],
      ["Explicit negative zero offset (-00:00)", "2026-11-01T08:00:00-00:00"],
      ["Millisecond precision with Z", "2026-11-01T08:00:00.123Z"],
      ["Millisecond precision with offset", "2026-11-01T08:00:00.456+05:30"],
      ["Leap day on a leap year (2024-02-29)", "2024-02-29T12:00:00Z"],
      ["Maximum global positive offset (+14:00)", "2026-11-01T08:00:00+14:00"],
      ["Minimum global negative offset (-12:00)", "2026-11-01T08:00:00-12:00"],
    ];

    it.each(validDatetimes)("should accept %s: %s", (_, datetime) => {
      const result = IsoDatetimeStringSchema.safeParse(datetime);
      expect(result.success).toBe(true);
      if (result.success) {
        // Must preserve string verbatim, not transform to Date object
        expect(typeof result.data).toBe("string");
        expect(result.data).toBe(datetime);
      }
    });
  });

  describe("Invalid datetime strings", () => {
    const invalidDatetimes = [
      ["Missing timezone information entirely", "2026-11-01T08:00:00"],
      ["Non-leap year February 29 (2026-02-29)", "2026-02-29T08:00:00Z"],
      ["31st day on 30-day month (April 31)", "2026-04-31T08:00:00Z"],
      ["31st day on 30-day month (November 31)", "2026-11-31T08:00:00Z"],
      ["Invalid month (Month 13)", "2026-13-01T08:00:00Z"],
      ["Invalid month (Month 00)", "2026-00-01T08:00:00Z"],
      ["Invalid day (Day 00)", "2026-01-00T08:00:00Z"],
      ["Invalid day (Day 32)", "2026-01-32T08:00:00Z"],
      ["Invalid hour (Hour 24)", "2026-11-01T24:00:00Z"],
      ["Invalid hour (Hour 25)", "2026-11-01T25:00:00Z"],
      ["Invalid minute (Minute 60)", "2026-11-01T08:60:00Z"],
      ["Invalid second (Second 60)", "2026-11-01T08:00:60Z"],
      ["Malformed timezone offset (+99:99)", "2026-11-01T08:00:00+99:99"],
      ["Malformed timezone offset hours (+25:00)", "2026-11-01T08:00:00+25:00"],
      ["Malformed timezone offset minutes (+05:60)", "2026-11-01T08:00:00+05:60"],
      ["Excessive positive offset (> +14:00)", "2026-11-01T08:00:00+14:01"],
      ["Excessive negative offset (< -12:00)", "2026-11-01T08:00:00-13:00"],
      ["Plain date without time or timezone", "2026-11-01"],
      ["Arbitrary text", "not-a-datetime"],
      ["Empty string", ""],
    ];

    it.each(invalidDatetimes)("should reject %s: %s", (_, datetime) => {
      const result = IsoDatetimeStringSchema.safeParse(datetime);
      expect(result.success).toBe(false);
    });

    it("should reject non-string values", () => {
      expect(IsoDatetimeStringSchema.safeParse(Date.now()).success).toBe(false);
      expect(IsoDatetimeStringSchema.safeParse(new Date()).success).toBe(false);
      expect(IsoDatetimeStringSchema.safeParse(null).success).toBe(false);
      expect(IsoDatetimeStringSchema.safeParse(undefined).success).toBe(false);
    });
  });
});

// ── 3. Core Scheduled Event Schema ───────────────────────────────────────────

describe("5.3 ScheduledEventSchema", () => {
  it("should validate a complete valid event", () => {
    const result = ScheduledEventSchema.safeParse(validScheduledEvent);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.eventId).toBe("evt-uuid-12345");
      expect(result.data.status).toBe("SCHEDULED");
      expect(result.data.prewarmWindowMinutes).toBe(60);
    }
  });

  it("should allow optional fields (description, expectedLoad, priority) to be omitted", () => {
    const minimalEvent = {
      eventId: "evt-002",
      eventName: "Minimal Flash Sale",
      eventType: "FLASH_SALE",
      startTime: "2026-12-01T00:00:00Z",
      endTime: "2026-12-01T06:00:00Z",
      prewarmWindowMinutes: 15,
      status: "SCHEDULED",
      createdAt: "2026-10-15T10:00:00Z",
      updatedAt: "2026-10-15T10:00:00Z",
    };
    const result = ScheduledEventSchema.safeParse(minimalEvent);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.description).toBeUndefined();
      expect(result.data.expectedLoad).toBeUndefined();
      expect(result.data.priority).toBeUndefined();
    }
  });

  it("should accept historical events in the past for research evaluation", () => {
    const pastEvent = {
      ...validScheduledEvent,
      startTime: "2020-01-01T00:00:00Z",
      endTime: "2020-01-01T12:00:00Z",
      createdAt: "2019-12-01T00:00:00Z",
      updatedAt: "2019-12-01T00:00:00Z",
    };
    const result = ScheduledEventSchema.safeParse(pastEvent);
    expect(result.success).toBe(true);
  });

  it("should trim eventName whitespace", () => {
    const event = {
      ...validScheduledEvent,
      eventName: "   Untrimmed Event Name   ",
    };
    const result = ScheduledEventSchema.safeParse(event);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.eventName).toBe("Untrimmed Event Name");
    }
  });

  it("should reject empty or whitespace-only eventName", () => {
    expect(
      ScheduledEventSchema.safeParse({ ...validScheduledEvent, eventName: "" }).success
    ).toBe(false);
    expect(
      ScheduledEventSchema.safeParse({ ...validScheduledEvent, eventName: "     " }).success
    ).toBe(false);
  });

  it("should reject eventName exceeding maximum length", () => {
    const longName = "A".repeat(EVENT_NAME_MAX_LENGTH + 1);
    const result = ScheduledEventSchema.safeParse({
      ...validScheduledEvent,
      eventName: longName,
    });
    expect(result.success).toBe(false);
  });

  it("should reject description exceeding maximum length", () => {
    const longDesc = "D".repeat(DESCRIPTION_MAX_LENGTH + 1);
    const result = ScheduledEventSchema.safeParse({
      ...validScheduledEvent,
      description: longDesc,
    });
    expect(result.success).toBe(false);
  });

  describe("Cross-field validation: endTime > startTime", () => {
    it("should reject when endTime is equal to startTime", () => {
      const sameTime = "2026-11-01T10:00:00Z";
      const result = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        startTime: sameTime,
        endTime: sameTime,
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].path).toContain("endTime");
        expect(result.error.issues[0].message).toContain("endTime must be later than startTime");
      }
    });

    it("should reject when endTime is earlier than startTime", () => {
      const result = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        startTime: "2026-11-01T18:00:00Z",
        endTime: "2026-11-01T08:00:00Z",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].path).toContain("endTime");
      }
    });

    it("should properly compare different timezone offsets (e.g. UTC vs +05:30)", () => {
      // 08:00 UTC = 13:30+05:30
      // 14:00+05:30 = 08:30 UTC -> later than 08:00 UTC
      const laterResult = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        startTime: "2026-11-01T08:00:00Z",
        endTime: "2026-11-01T14:00:00+05:30",
      });
      expect(laterResult.success).toBe(true);

      // 13:00+05:30 = 07:30 UTC -> earlier than 08:00 UTC
      const earlierResult = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        startTime: "2026-11-01T08:00:00Z",
        endTime: "2026-11-01T13:00:00+05:30",
      });
      expect(earlierResult.success).toBe(false);
    });
  });

  describe("prewarmWindowMinutes bounds", () => {
    it("should accept prewarmWindowMinutes at lower limit (0)", () => {
      const result = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        prewarmWindowMinutes: PREWARM_WINDOW_MIN_MINUTES,
      });
      expect(result.success).toBe(true);
    });

    it("should accept prewarmWindowMinutes at upper limit (10080 = 7 days)", () => {
      const result = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        prewarmWindowMinutes: PREWARM_WINDOW_MAX_MINUTES,
      });
      expect(result.success).toBe(true);
    });

    it("should reject negative prewarmWindowMinutes", () => {
      const result = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        prewarmWindowMinutes: -1,
      });
      expect(result.success).toBe(false);
    });

    it("should reject non-integer prewarmWindowMinutes", () => {
      const result = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        prewarmWindowMinutes: 30.5,
      });
      expect(result.success).toBe(false);
    });

    it("should reject prewarmWindowMinutes exceeding maximum (10081)", () => {
      const result = ScheduledEventSchema.safeParse({
        ...validScheduledEvent,
        prewarmWindowMinutes: PREWARM_WINDOW_MAX_MINUTES + 1,
      });
      expect(result.success).toBe(false);
    });
  });

  it("should reject unknown properties (strict)", () => {
    const result = ScheduledEventSchema.safeParse({
      ...validScheduledEvent,
      extraField: "unexpected",
    });
    expect(result.success).toBe(false);
  });
});

// ── 4. Create Event Schema ───────────────────────────────────────────────────

describe("5.4 CreateScheduledEventInputSchema", () => {
  const validCreatePayload = {
    eventName: "New Promotional Campaign",
    eventType: "PROMOTIONAL_CAMPAIGN",
    description: "Black Friday promotion",
    startTime: "2026-11-25T00:00:00Z",
    endTime: "2026-11-28T23:59:59Z",
    expectedLoad: "VERY_HIGH",
    priority: "CRITICAL",
    prewarmWindowMinutes: 120,
  };

  it("should accept valid payload with all editable fields", () => {
    const result = CreateScheduledEventInputSchema.safeParse(validCreatePayload);
    expect(result.success).toBe(true);
  });

  it("should accept valid payload with required fields only", () => {
    const requiredOnly = {
      eventName: "New Promotional Campaign",
      eventType: "PROMOTIONAL_CAMPAIGN",
      startTime: "2026-11-25T00:00:00Z",
      endTime: "2026-11-28T23:59:59Z",
      prewarmWindowMinutes: 0,
    };
    const result = CreateScheduledEventInputSchema.safeParse(requiredOnly);
    expect(result.success).toBe(true);
  });

  describe("Rejection of system-managed fields (strict protection)", () => {
    it.each([
      ["eventId", "evt-client-injected-id"],
      ["status", "COMPLETED"],
      ["createdAt", "2026-10-15T10:00:00Z"],
      ["updatedAt", "2026-10-15T10:00:00Z"],
    ])("should reject client-supplied system field %s", (field, val) => {
      const payload = {
        ...validCreatePayload,
        [field]: val,
      };
      const result = CreateScheduledEventInputSchema.safeParse(payload);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].code).toBe("unrecognized_keys");
      }
    });
  });

  it("should reject unknown client-supplied properties", () => {
    const payload = {
      ...validCreatePayload,
      customAdminFlag: true,
    };
    const result = CreateScheduledEventInputSchema.safeParse(payload);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].code).toBe("unrecognized_keys");
    }
  });

  it("should reject missing required fields", () => {
    // Missing eventName
    const withoutName = { ...validCreatePayload };
    delete (withoutName as Record<string, unknown>).eventName;
    expect(CreateScheduledEventInputSchema.safeParse(withoutName).success).toBe(false);

    // Missing eventType
    const withoutType = { ...validCreatePayload };
    delete (withoutType as Record<string, unknown>).eventType;
    expect(CreateScheduledEventInputSchema.safeParse(withoutType).success).toBe(false);

    // Missing startTime
    const withoutStart = { ...validCreatePayload };
    delete (withoutStart as Record<string, unknown>).startTime;
    expect(CreateScheduledEventInputSchema.safeParse(withoutStart).success).toBe(false);

    // Missing endTime
    const withoutEnd = { ...validCreatePayload };
    delete (withoutEnd as Record<string, unknown>).endTime;
    expect(CreateScheduledEventInputSchema.safeParse(withoutEnd).success).toBe(false);

    // Missing prewarmWindowMinutes
    const withoutPrewarm = { ...validCreatePayload };
    delete (withoutPrewarm as Record<string, unknown>).prewarmWindowMinutes;
    expect(CreateScheduledEventInputSchema.safeParse(withoutPrewarm).success).toBe(false);
  });

  it("should enforce endTime > startTime on create", () => {
    const invalidDates = {
      ...validCreatePayload,
      startTime: "2026-11-28T23:59:59Z",
      endTime: "2026-11-25T00:00:00Z",
    };
    const result = CreateScheduledEventInputSchema.safeParse(invalidDates);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toContain("endTime");
    }
  });
});

// ── 5. Update Event Schema ───────────────────────────────────────────────────

describe("5.5 UpdateScheduledEventInputSchema", () => {
  it("should accept valid single-field partial update", () => {
    const result = UpdateScheduledEventInputSchema.safeParse({
      eventName: "Renamed Event",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.eventName).toBe("Renamed Event");
    }
  });

  it("should accept valid multi-field partial update", () => {
    const result = UpdateScheduledEventInputSchema.safeParse({
      eventName: "Renamed Event",
      expectedLoad: "MEDIUM",
      priority: "LOW",
      prewarmWindowMinutes: 45,
    });
    expect(result.success).toBe(true);
  });

  it("should reject an empty update object", () => {
    const result = UpdateScheduledEventInputSchema.safeParse({});
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toContain("Update payload must not be empty");
    }
  });

  describe("Rejection of system-managed fields on update", () => {
    it.each([
      ["eventId", "new-id"],
      ["status", "CANCELLED"],
      ["createdAt", "2026-10-15T10:00:00Z"],
      ["updatedAt", "2026-10-15T10:00:00Z"],
    ])("should reject updating system field %s", (field, val) => {
      const result = UpdateScheduledEventInputSchema.safeParse({
        eventName: "Updated",
        [field]: val,
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].code).toBe("unrecognized_keys");
      }
    });
  });

  it("should reject unknown properties on update", () => {
    const result = UpdateScheduledEventInputSchema.safeParse({
      eventName: "Updated",
      unsupportedField: 42,
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].code).toBe("unrecognized_keys");
    }
  });

  describe("Cross-field datetime update behavior", () => {
    it("should accept update supplying both startTime and endTime when endTime > startTime", () => {
      const result = UpdateScheduledEventInputSchema.safeParse({
        startTime: "2026-11-10T10:00:00Z",
        endTime: "2026-11-10T14:00:00Z",
      });
      expect(result.success).toBe(true);
    });

    it("should reject update supplying both startTime and endTime when endTime <= startTime", () => {
      const result = UpdateScheduledEventInputSchema.safeParse({
        startTime: "2026-11-10T14:00:00Z",
        endTime: "2026-11-10T10:00:00Z",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].path).toContain("endTime");
        expect(result.error.issues[0].message).toContain("endTime must be later than startTime");
      }
    });

    it("should accept update supplying ONLY startTime (comparison against existing DB record happens in service layer)", () => {
      // Standalone schema cannot validate against unseen persisted record
      const result = UpdateScheduledEventInputSchema.safeParse({
        startTime: "2026-11-10T10:00:00Z",
      });
      expect(result.success).toBe(true);
    });

    it("should accept update supplying ONLY endTime (comparison against existing DB record happens in service layer)", () => {
      // Standalone schema cannot validate against unseen persisted record
      const result = UpdateScheduledEventInputSchema.safeParse({
        endTime: "2026-11-10T18:00:00Z",
      });
      expect(result.success).toBe(true);
    });
  });
});

// ── 6. Response Schemas ──────────────────────────────────────────────────────

describe("5.6 Response Schemas", () => {
  describe("PaginationMetaSchema", () => {
    it("should validate standard pagination metadata", () => {
      const meta = {
        total: 100,
        page: 1,
        limit: 20,
        totalPages: 5,
      };
      const result = PaginationMetaSchema.safeParse(meta);
      expect(result.success).toBe(true);
    });

    it("should validate pagination metadata with remainder page", () => {
      // Math.ceil(25 / 10) = 3
      const meta = {
        total: 25,
        page: 3,
        limit: 10,
        totalPages: 3,
      };
      const result = PaginationMetaSchema.safeParse(meta);
      expect(result.success).toBe(true);
    });

    it("should validate empty pagination metadata (total = 0, totalPages = 0)", () => {
      const meta = {
        total: 0,
        page: 1,
        limit: 20,
        totalPages: 0,
      };
      const result = PaginationMetaSchema.safeParse(meta);
      expect(result.success).toBe(true);
    });

    it("should reject inconsistent totalPages", () => {
      // total: 100, limit: 20 -> totalPages must be 5, but 9 provided
      const meta = {
        total: 100,
        page: 1,
        limit: 20,
        totalPages: 9,
      };
      const result = PaginationMetaSchema.safeParse(meta);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].path).toContain("totalPages");
        expect(result.error.issues[0].message).toContain("totalPages must be consistent");
      }
    });

    it("should reject negative total", () => {
      expect(
        PaginationMetaSchema.safeParse({ total: -1, page: 1, limit: 10, totalPages: 0 }).success
      ).toBe(false);
    });

    it("should reject page < 1", () => {
      expect(
        PaginationMetaSchema.safeParse({ total: 10, page: 0, limit: 10, totalPages: 1 }).success
      ).toBe(false);
    });

    it("should reject limit < 1", () => {
      expect(
        PaginationMetaSchema.safeParse({ total: 10, page: 1, limit: 0, totalPages: 1 }).success
      ).toBe(false);
    });

    it("should reject limit exceeding maximum limit (1000)", () => {
      expect(
        PaginationMetaSchema.safeParse({
          total: 10,
          page: 1,
          limit: PAGINATION_LIMIT_MAX + 1,
          totalPages: 1,
        }).success
      ).toBe(false);
    });

    it("should reject non-integer pagination numbers", () => {
      expect(
        PaginationMetaSchema.safeParse({ total: 10.5, page: 1, limit: 10, totalPages: 1 }).success
      ).toBe(false);
      expect(
        PaginationMetaSchema.safeParse({ total: 10, page: 1.2, limit: 10, totalPages: 1 }).success
      ).toBe(false);
    });
  });

  describe("EventResponseSchema", () => {
    it("should validate a single event response", () => {
      const response = {
        event: validScheduledEvent,
      };
      const result = EventResponseSchema.safeParse(response);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.event.eventId).toBe("evt-uuid-12345");
      }
    });

    it("should reject event response with invalid event payload", () => {
      const badResponse = {
        event: { ...validScheduledEvent, eventName: "" },
      };
      expect(EventResponseSchema.safeParse(badResponse).success).toBe(false);
    });
  });

  describe("EventListResponseSchema", () => {
    it("should validate a list response with multiple events and pagination metadata", () => {
      const listResponse = {
        events: [validScheduledEvent],
        pagination: {
          total: 1,
          page: 1,
          limit: 10,
          totalPages: 1,
        },
      };
      const result = EventListResponseSchema.safeParse(listResponse);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.events).toHaveLength(1);
        expect(result.data.pagination.total).toBe(1);
      }
    });

    it("should validate an empty list response", () => {
      const emptyResponse = {
        events: [],
        pagination: {
          total: 0,
          page: 1,
          limit: 20,
          totalPages: 0,
        },
      };
      const result = EventListResponseSchema.safeParse(emptyResponse);
      expect(result.success).toBe(true);
    });
  });
});

// ── 7. Error Handling & Security ─────────────────────────────────────────────

describe("8. Error Handling & Security", () => {
  it("should provide structured field paths in validation errors without leaking internals", () => {
    const invalidInput = {
      eventName: "",
      eventType: "INVALID_ENUM_VALUE",
      startTime: "invalid-date",
      endTime: "invalid-date",
      prewarmWindowMinutes: -10,
    };
    const result = CreateScheduledEventInputSchema.safeParse(invalidInput);
    expect(result.success).toBe(false);
    if (!result.success) {
      const fieldPaths = result.error.issues.map((i) => i.path.join("."));
      expect(fieldPaths).toContain("eventName");
      expect(fieldPaths).toContain("eventType");
      expect(fieldPaths).toContain("startTime");
      expect(fieldPaths).toContain("endTime");
      expect(fieldPaths).toContain("prewarmWindowMinutes");

      // Verify no sensitive internal strings or system details exist in error messages
      const errorJson = JSON.stringify(result.error.format());
      expect(errorJson).not.toContain("process.env");
      expect(errorJson).not.toContain("password");
      expect(errorJson).not.toContain("mongodb");
      expect(errorJson).not.toContain("stack");
    }
  });
});
