// ─────────────────────────────────────────────────────────────────────────────
// Event Validation Schemas — Component 4
// "Event Intelligence & Context-Aware Feature Engineering"
//
// This module defines runtime validation schemas using Zod for event-related
// data contracts. These schemas ensure strict data integrity across API
// requests, frontend forms, database persistence, and pipeline ingestion.
// ─────────────────────────────────────────────────────────────────────────────

import { z } from "zod";
import {
  EVENT_TYPES,
  EXPECTED_LOADS,
  EVENT_PRIORITIES,
  EVENT_STATUSES,
  type EventType,
  type ExpectedLoad,
  type EventPriority,
  type EventStatus,
  type ScheduledEvent,
  type CreateScheduledEventInput,
  type UpdateScheduledEventInput,
  type PaginationMeta,
  type EventResponse,
  type EventListResponse,
  type ListEventsQuery,
} from "../types/index.js";

// ── Validation Limits & Constraints ──────────────────────────────────────────

export const EVENT_NAME_MIN_LENGTH = 1 as const;
export const EVENT_NAME_MAX_LENGTH = 200 as const;
export const DESCRIPTION_MAX_LENGTH = 2000 as const;
export const PREWARM_WINDOW_MIN_MINUTES = 0 as const;
export const PREWARM_WINDOW_MAX_MINUTES = 10080 as const; // 7 days in minutes (7 * 24 * 60)
export const PAGINATION_PAGE_MIN = 1 as const;
export const PAGINATION_LIMIT_MIN = 1 as const;
export const PAGINATION_LIMIT_MAX = 1000 as const;

// ── 5.1 Enum Schemas ─────────────────────────────────────────────────────────

/**
 * Zod schema for EventType.
 * Reuses the canonical EVENT_TYPES constant array as the single source of truth.
 */
export const EventTypeSchema = z.enum(EVENT_TYPES as [EventType, ...EventType[]], {
  errorMap: () => ({
    message: `Invalid eventType. Allowed values: ${EVENT_TYPES.join(", ")}`,
  }),
});

/**
 * Zod schema for ExpectedLoad.
 * Reuses the canonical EXPECTED_LOADS constant array.
 */
export const ExpectedLoadSchema = z.enum(EXPECTED_LOADS as [ExpectedLoad, ...ExpectedLoad[]], {
  errorMap: () => ({
    message: `Invalid expectedLoad. Allowed values: ${EXPECTED_LOADS.join(", ")}`,
  }),
});

/**
 * Zod schema for EventPriority.
 * Reuses the canonical EVENT_PRIORITIES constant array.
 */
export const EventPrioritySchema = z.enum(EVENT_PRIORITIES as [EventPriority, ...EventPriority[]], {
  errorMap: () => ({
    message: `Invalid priority. Allowed values: ${EVENT_PRIORITIES.join(", ")}`,
  }),
});

/**
 * Zod schema for EventStatus.
 * Reuses the canonical EVENT_STATUSES constant array.
 */
export const EventStatusSchema = z.enum(EVENT_STATUSES as [EventStatus, ...EventStatus[]], {
  errorMap: () => ({
    message: `Invalid status. Allowed values: ${EVENT_STATUSES.join(", ")}`,
  }),
});

// ── 5.2 Datetime Validation ──────────────────────────────────────────────────

/**
 * Reusable ISO 8601 datetime validation rule with explicit timezone enforcement.
 *
 * Requirements satisfied:
 * 1. Requires a string input (z.string()).
 * 2. Requires a valid ISO 8601 datetime representation.
 * 3. Requires an explicit timezone offset, either UTC ('Z') or valid numeric offset (e.g., '+05:30', '-08:00').
 *    Local datetime strings without timezone are rejected.
 * 4. Rejects invalid calendar dates (such as February 29 in non-leap years or non-existent month dates).
 * 5. Rejects malformed timezone offsets (e.g., hours > 14, minutes > 59, or offset hours < -12).
 * 6. Does not convert the string to a Date object — preserves the validated ISO string verbatim.
 */
export const IsoDatetimeStringSchema = z
  .string({
    required_error: "Datetime is required",
    invalid_type_error: "Datetime must be a string",
  })
  .datetime({
    offset: true,
    message:
      "Must be a valid ISO 8601 datetime string with timezone (e.g. '2026-11-01T08:00:00Z' or '2026-11-01T08:00:00+05:30')",
  })
  .refine(
    (val) => {
      // Step 1: Reject unparseable calendar dates via Date.parse (returns NaN for invalid dates)
      if (Number.isNaN(Date.parse(val))) {
        return false;
      }

      // Step 2: Validate timezone offset range.
      // Standard UTC offsets on Earth span from -12:00 to +14:00.
      // Zod's internal regex accepts any \d{2}:?\d{2}, so this check guards against
      // invalid offsets such as +99:99, +25:00, +05:60, or -15:00.
      const offsetMatch = val.match(/([+-])(\d{2}):?(\d{2})$/);
      if (offsetMatch) {
        const sign = offsetMatch[1];
        const hours = parseInt(offsetMatch[2], 10);
        const minutes = parseInt(offsetMatch[3], 10);

        if (minutes > 59) {
          return false;
        }

        if (sign === "+" && (hours > 14 || (hours === 14 && minutes > 0))) {
          return false;
        }

        if (sign === "-" && (hours > 12 || (hours === 12 && minutes > 0))) {
          return false;
        }
      }

      return true;
    },
    {
      message:
        "Datetime must represent a valid calendar date and a valid UTC offset (between -12:00 and +14:00 with minutes 00-59)",
    }
  );

/** Alias for convenience */
export const isoDatetimeSchema = IsoDatetimeStringSchema;

// ── Reusable Field Definitions ───────────────────────────────────────────────

const eventFields = {
  eventId: z
    .string({
      required_error: "eventId is required",
      invalid_type_error: "eventId must be a string",
    })
    .trim()
    .min(1, "eventId must not be empty"),

  eventName: z
    .string({
      required_error: "eventName is required",
      invalid_type_error: "eventName must be a string",
    })
    .trim()
    .min(EVENT_NAME_MIN_LENGTH, "eventName must not be empty")
    .max(EVENT_NAME_MAX_LENGTH, `eventName must not exceed ${EVENT_NAME_MAX_LENGTH} characters`),

  eventType: EventTypeSchema,

  description: z
    .string({
      invalid_type_error: "description must be a string",
    })
    .max(DESCRIPTION_MAX_LENGTH, `description must not exceed ${DESCRIPTION_MAX_LENGTH} characters`)
    .optional(),

  startTime: IsoDatetimeStringSchema,

  endTime: IsoDatetimeStringSchema,

  expectedLoad: ExpectedLoadSchema.optional(),

  priority: EventPrioritySchema.optional(),

  prewarmWindowMinutes: z
    .number({
      required_error: "prewarmWindowMinutes is required",
      invalid_type_error: "prewarmWindowMinutes must be a number",
    })
    .int("prewarmWindowMinutes must be an integer")
    .min(PREWARM_WINDOW_MIN_MINUTES, `prewarmWindowMinutes must be at least ${PREWARM_WINDOW_MIN_MINUTES}`)
    .max(PREWARM_WINDOW_MAX_MINUTES, `prewarmWindowMinutes must not exceed ${PREWARM_WINDOW_MAX_MINUTES} minutes`),

  status: EventStatusSchema,

  createdAt: IsoDatetimeStringSchema,

  updatedAt: IsoDatetimeStringSchema,
};

// ── 5.3 Core Scheduled Event Schema ──────────────────────────────────────────

/**
 * Complete runtime validation schema for ScheduledEvent.
 * Validates the full domain entity, including system-managed fields and cross-field rules.
 */
export const ScheduledEventSchema = z
  .object(eventFields)
  .strict()
  .refine(
    (event) => new Date(event.endTime).getTime() > new Date(event.startTime).getTime(),
    {
      message: "endTime must be later than startTime",
      path: ["endTime"],
    }
  );

// ── 5.4 Create Event Schema ──────────────────────────────────────────────────

/**
 * Base user-editable fields for event creation.
 * Excludes system-managed properties: eventId, status, createdAt, updatedAt.
 */
const createFields = {
  eventName: eventFields.eventName,
  eventType: eventFields.eventType,
  description: eventFields.description,
  startTime: eventFields.startTime,
  endTime: eventFields.endTime,
  expectedLoad: eventFields.expectedLoad,
  priority: eventFields.priority,
  prewarmWindowMinutes: eventFields.prewarmWindowMinutes,
};

const createBaseObject = z.object(createFields).strict();

/**
 * Runtime validation schema for CreateScheduledEventInput.
 *
 * Enforces:
 * - Only user-editable fields are accepted.
 * - System-managed fields (eventId, status, createdAt, updatedAt) and unknown properties are explicitly rejected.
 * - endTime must be later than startTime.
 */
export const CreateScheduledEventInputSchema = createBaseObject.refine(
  (input) => new Date(input.endTime).getTime() > new Date(input.startTime).getTime(),
  {
    message: "endTime must be later than startTime",
    path: ["endTime"],
  }
);

// ── 5.5 Update Event Schema ──────────────────────────────────────────────────

const updateBaseObject = createBaseObject.partial();

/**
 * Runtime validation schema for UpdateScheduledEventInput.
 *
 * Enforces:
 * - All editable fields are optional.
 * - System-managed fields and unknown properties are explicitly rejected (.strict() inherited).
 * - Empty update payload is rejected (at least one field must be provided).
 * - Cross-field check: when both startTime and endTime are provided, endTime must be later than startTime.
 *
 * Note: When only one of startTime or endTime is supplied in a partial update,
 * comparison against the existing persisted record cannot be evaluated by this standalone schema.
 * That validation must be performed in the application/service layer against the database record.
 */
export const UpdateScheduledEventInputSchema = updateBaseObject
  .refine(
    (input) => Object.keys(input).length > 0,
    {
      message: "Update payload must not be empty; at least one field must be provided",
    }
  )
  .refine(
    (input) => {
      if (input.startTime !== undefined && input.endTime !== undefined) {
        return new Date(input.endTime).getTime() > new Date(input.startTime).getTime();
      }
      return true;
    },
    {
      message: "endTime must be later than startTime when both are provided",
      path: ["endTime"],
    }
  );

// ── 5.6 Response Schemas ─────────────────────────────────────────────────────

/**
 * Runtime validation schema for PaginationMeta.
 * Validates integer boundaries and cross-field mathematical consistency.
 */
export const PaginationMetaSchema = z
  .object({
    total: z
      .number({
        required_error: "total is required",
        invalid_type_error: "total must be a number",
      })
      .int("total must be an integer")
      .min(0, "total cannot be negative"),

    page: z
      .number({
        required_error: "page is required",
        invalid_type_error: "page must be a number",
      })
      .int("page must be an integer")
      .min(PAGINATION_PAGE_MIN, `page must be at least ${PAGINATION_PAGE_MIN}`),

    limit: z
      .number({
        required_error: "limit is required",
        invalid_type_error: "limit must be a number",
      })
      .int("limit must be an integer")
      .min(PAGINATION_LIMIT_MIN, `limit must be at least ${PAGINATION_LIMIT_MIN}`)
      .max(PAGINATION_LIMIT_MAX, `limit must not exceed ${PAGINATION_LIMIT_MAX}`),

    totalPages: z
      .number({
        required_error: "totalPages is required",
        invalid_type_error: "totalPages must be a number",
      })
      .int("totalPages must be an integer")
      .min(0, "totalPages cannot be negative"),
  })
  .strict()
  .refine(
    (meta) => {
      // Consistency check: totalPages must match Math.ceil(total / limit)
      if (meta.total === 0) {
        return meta.totalPages <= 1;
      }
      return meta.totalPages === Math.ceil(meta.total / meta.limit);
    },
    {
      message: "totalPages must be consistent with total and limit (Math.ceil(total / limit))",
      path: ["totalPages"],
    }
  );

/**
 * Runtime validation schema for EventResponse.
 */
export const EventResponseSchema = z
  .object({
    event: ScheduledEventSchema,
  })
  .strict();

/**
 * Runtime validation schema for EventListResponse.
 */
export const EventListResponseSchema = z
  .object({
    events: z.array(ScheduledEventSchema),
    pagination: PaginationMetaSchema,
  })
  .strict();

/**
 * Runtime validation schema for event query filters and pagination.
 */
export const ListEventsQuerySchema = z
  .object({
    page: z.coerce
      .number()
      .int("page must be an integer")
      .min(PAGINATION_PAGE_MIN, `page must be at least ${PAGINATION_PAGE_MIN}`)
      .optional(),
    limit: z.coerce
      .number()
      .int("limit must be an integer")
      .min(PAGINATION_LIMIT_MIN, `limit must be at least ${PAGINATION_LIMIT_MIN}`)
      .max(100, "limit cannot exceed 100 per page")
      .optional(),
    status: EventStatusSchema.optional(),
    eventType: EventTypeSchema.optional(),
    priority: EventPrioritySchema.optional(),
    expectedLoad: ExpectedLoadSchema.optional(),
    startDateFrom: IsoDatetimeStringSchema.optional(),
    startDateTo: IsoDatetimeStringSchema.optional(),
    sortBy: z.enum(["startTime", "createdAt", "eventName"]).optional(),
    sortOrder: z.enum(["asc", "desc"]).optional(),
  })
  .strict()
  .refine(
    (query) => {
      if (query.startDateFrom && query.startDateTo) {
        return (
          new Date(query.startDateTo).getTime() >=
          new Date(query.startDateFrom).getTime()
        );
      }
      return true;
    },
    {
      message: "startDateTo must be later than or equal to startDateFrom",
      path: ["startDateTo"],
    }
  );

// ── Type Inference & Compatibility Exports ───────────────────────────────────

export type ScheduledEventSchemaType = z.infer<typeof ScheduledEventSchema>;
export type CreateScheduledEventInputSchemaType = z.infer<typeof CreateScheduledEventInputSchema>;
export type UpdateScheduledEventInputSchemaType = z.infer<typeof UpdateScheduledEventInputSchema>;
export type PaginationMetaSchemaType = z.infer<typeof PaginationMetaSchema>;
export type EventResponseSchemaType = z.infer<typeof EventResponseSchema>;
export type EventListResponseSchemaType = z.infer<typeof EventListResponseSchema>;
export type ListEventsQuerySchemaType = z.infer<typeof ListEventsQuerySchema>;

// Compile-time verification that inferred schema types are mutually assignable
// with the canonical TypeScript interfaces from Part 1.2
type IsAssignable<A, B> = A extends B ? (B extends A ? true : false) : false;

type _AssertScheduledEvent = IsAssignable<ScheduledEventSchemaType, ScheduledEvent>;
type _AssertCreateInput = IsAssignable<CreateScheduledEventInputSchemaType, CreateScheduledEventInput>;
type _AssertUpdateInput = IsAssignable<UpdateScheduledEventInputSchemaType, UpdateScheduledEventInput>;
type _AssertPaginationMeta = IsAssignable<PaginationMetaSchemaType, PaginationMeta>;
type _AssertEventResponse = IsAssignable<EventResponseSchemaType, EventResponse>;
type _AssertEventListResponse = IsAssignable<EventListResponseSchemaType, EventListResponse>;
type _AssertListEventsQuery = IsAssignable<ListEventsQuerySchemaType, ListEventsQuery>;

// Compile-time checks (will cause build failure if any assertion evaluates to false)
const _typeChecks: [
  _AssertScheduledEvent,
  _AssertCreateInput,
  _AssertUpdateInput,
  _AssertPaginationMeta,
  _AssertEventResponse,
  _AssertEventListResponse,
  _AssertListEventsQuery
] = [true, true, true, true, true, true, true];
void _typeChecks;
