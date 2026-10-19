// ─────────────────────────────────────────────────────────────────────────────
// Sample Event Fixtures & Seed Data — Component 4
// "Event Intelligence & Context-Aware Feature Engineering"
//
// This module provides deterministic, reusable sample fixtures representing
// realistic business events within a university digital ecosystem (LMS,
// student portal, registration, bookstore, payment gateway).
//
// These fixtures are used across:
//   - Unit and integration testing
//   - Local development seed data
//   - Event Management API validation
//   - Future pipeline and feature engineering simulation
//
// Architectural Boundaries:
//   - No database connections, queries, or Mongoose/MongoDB dependencies.
//   - No cache keys, TTL values, eviction policies, or Redis operations.
//   - Pure data contracts only; completely side-effect free.
// ─────────────────────────────────────────────────────────────────────────────

import type {
  ScheduledEvent,
  CreateScheduledEventInput,
} from "../types/index.js";

// ── 1. Complete ScheduledEvent Fixtures ───────────────────────────────────────

/**
 * 1. University examination result release.
 * High-concurrency event on student portal and grading microservices.
 */
export const FIXTURE_RESULT_RELEASE: ScheduledEvent = {
  eventId: "EVT-FIXTURE-001",
  eventName: "Semester 1 Examination Results Release",
  eventType: "RESULT_RELEASE",
  description:
    "Official publication of semester 1 course grades and GPA standings across all academic faculties on the student portal.",
  startTime: "2026-11-15T08:00:00+05:30",
  endTime: "2026-11-15T18:00:00+05:30",
  expectedLoad: "VERY_HIGH",
  priority: "CRITICAL",
  prewarmWindowMinutes: 60,
  status: "SCHEDULED",
  createdAt: "2026-10-01T09:00:00Z",
  updatedAt: "2026-10-01T09:00:00Z",
};

/**
 * 2. Student semester registration opening.
 * Massive concurrent writes and queries against course catalog and enrollment services.
 */
export const FIXTURE_REGISTRATION_OPENING: ScheduledEvent = {
  eventId: "EVT-FIXTURE-002",
  eventName: "Academic Year 2026/2027 Course Registration",
  eventType: "REGISTRATION",
  description:
    "Self-service elective and core course enrollment window for continuing undergraduate students.",
  startTime: "2026-11-20T09:00:00+05:30",
  endTime: "2026-11-25T17:00:00+05:30",
  expectedLoad: "HIGH",
  priority: "HIGH",
  prewarmWindowMinutes: 45,
  status: "SCHEDULED",
  createdAt: "2026-10-05T10:00:00Z",
  updatedAt: "2026-10-05T10:00:00Z",
};

/**
 * 3. Online flash sale.
 * Rapid spike in traffic on inventory and checkout microservices.
 */
export const FIXTURE_FLASH_SALE: ScheduledEvent = {
  eventId: "EVT-FIXTURE-003",
  eventName: "Campus Bookstore Digital Textbook Flash Sale",
  eventType: "FLASH_SALE",
  description:
    "Four-hour limited flash discount on mandatory digital course materials, e-textbooks, and academic stationery.",
  startTime: "2026-11-28T12:00:00Z",
  endTime: "2026-11-28T16:00:00Z",
  expectedLoad: "HIGH",
  priority: "HIGH",
  prewarmWindowMinutes: 30,
  status: "SCHEDULED",
  createdAt: "2026-10-10T11:00:00Z",
  updatedAt: "2026-10-10T11:00:00Z",
};

/**
 * 4. Ticket release for a popular event.
 * Sudden concentrated reservation attempts on ticketing and payment services.
 */
export const FIXTURE_TICKET_RELEASE: ScheduledEvent = {
  eventId: "EVT-FIXTURE-004",
  eventName: "Annual University Tech Symposium Pass Release",
  eventType: "TICKET_RELEASE",
  description:
    "General admission ticket reservation launch for the national student research conference and keynote sessions.",
  startTime: "2026-12-01T10:00:00+05:30",
  endTime: "2026-12-01T14:00:00+05:30",
  expectedLoad: "HIGH",
  priority: "MEDIUM",
  prewarmWindowMinutes: 30,
  status: "SCHEDULED",
  createdAt: "2026-10-12T08:30:00Z",
  updatedAt: "2026-10-12T08:30:00Z",
};

/**
 * 5. Promotional campaign.
 * Extended marketing campaign with distributed medium-intensity traffic.
 */
export const FIXTURE_PROMOTIONAL_CAMPAIGN: ScheduledEvent = {
  eventId: "EVT-FIXTURE-005",
  eventName: "Postgraduate Open Day Awareness Week",
  eventType: "PROMOTIONAL_CAMPAIGN",
  description:
    "Targeted awareness campaign for prospective master's and doctoral degree applicants across faculty information pages.",
  startTime: "2026-12-05T00:00:00Z",
  endTime: "2026-12-12T23:59:59Z",
  expectedLoad: "MEDIUM",
  priority: "MEDIUM",
  prewarmWindowMinutes: 15,
  status: "SCHEDULED",
  createdAt: "2026-10-14T14:00:00Z",
  updatedAt: "2026-10-14T14:00:00Z",
};

/**
 * 6. Payment deadline.
 * Critical end-of-window surge on finance and gateway endpoints.
 */
export const FIXTURE_PAYMENT_DEADLINE: ScheduledEvent = {
  eventId: "EVT-FIXTURE-006",
  eventName: "Semester Tuition Fee Final Settlement Deadline",
  eventType: "PAYMENT_DEADLINE",
  description:
    "Final cut-off for semester tuition, lab fees, and accommodation charges through the integrated banking gateway.",
  startTime: "2026-12-15T08:00:00+05:30",
  endTime: "2026-12-15T23:59:59+05:30",
  expectedLoad: "VERY_HIGH",
  priority: "CRITICAL",
  prewarmWindowMinutes: 60,
  status: "SCHEDULED",
  createdAt: "2026-10-15T12:00:00Z",
  updatedAt: "2026-10-15T12:00:00Z",
};

/**
 * 7. Low-demand scheduled event.
 * Minimal footprint; tests graceful handling of low prewarm requirements without over-provisioning.
 */
export const FIXTURE_LOW_DEMAND_EVENT: ScheduledEvent = {
  eventId: "EVT-FIXTURE-007",
  eventName: "Off-Campus Archival Research Seminar Registration",
  eventType: "OTHER",
  description:
    "Registration sign-up for small-cohort faculty archival workshop; limited to 25 researchers.",
  startTime: "2026-12-20T10:00:00Z",
  endTime: "2026-12-20T12:00:00Z",
  expectedLoad: "LOW",
  priority: "LOW",
  prewarmWindowMinutes: 5,
  status: "SCHEDULED",
  createdAt: "2026-10-16T08:00:00Z",
  updatedAt: "2026-10-16T08:00:00Z",
};

/**
 * 8. Completed historical event.
 * Past event record; ensures historical data remains valid and does not trigger scheduling actions.
 */
export const FIXTURE_COMPLETED_EVENT: ScheduledEvent = {
  eventId: "EVT-FIXTURE-008",
  eventName: "Mid-Semester Continuous Assessment Quiz Results",
  eventType: "RESULT_RELEASE",
  description:
    "Historical mid-semester quiz marks release; event window has successfully concluded.",
  startTime: "2026-09-01T08:00:00+05:30",
  endTime: "2026-09-01T16:00:00+05:30",
  expectedLoad: "MEDIUM",
  priority: "MEDIUM",
  prewarmWindowMinutes: 30,
  status: "COMPLETED",
  createdAt: "2026-08-20T10:00:00Z",
  updatedAt: "2026-09-01T16:05:00Z",
};

/**
 * 9. Cancelled event.
 * Lifecycle verification for events called off before start; must not trigger prewarm.
 */
export const FIXTURE_CANCELLED_EVENT: ScheduledEvent = {
  eventId: "EVT-FIXTURE-009",
  eventName: "Inter-University Sports Gala Ticket Sale",
  eventType: "TICKET_RELEASE",
  description:
    "Cancelled due to tournament rescheduling; record retained in repository for audit trail.",
  startTime: "2026-10-05T09:00:00Z",
  endTime: "2026-10-05T17:00:00Z",
  expectedLoad: "MEDIUM",
  priority: "LOW",
  prewarmWindowMinutes: 15,
  status: "CANCELLED",
  createdAt: "2026-09-25T11:00:00Z",
  updatedAt: "2026-10-01T15:30:00Z",
};

/**
 * 10. Currently processing event.
 * Active event window; tests the PROCESSING lifecycle state.
 */
export const FIXTURE_PROCESSING_EVENT: ScheduledEvent = {
  eventId: "EVT-FIXTURE-010",
  eventName: "Library Digital Resource Catalog Migration Window",
  eventType: "OTHER",
  description:
    "Active scheduled maintenance window currently in progress; requests routed through cached fallbacks.",
  startTime: "2026-10-16T06:00:00Z",
  endTime: "2026-10-16T22:00:00Z",
  expectedLoad: "UNKNOWN",
  priority: "LOW",
  prewarmWindowMinutes: 10,
  status: "PROCESSING",
  createdAt: "2026-10-15T18:00:00Z",
  updatedAt: "2026-10-16T06:00:00Z",
};

/**
 * Canonical collection of all valid complete scheduled event fixtures.
 */
export const SAMPLE_SCHEDULED_EVENTS: readonly ScheduledEvent[] = [
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
] as const;

// ── 2. CreateScheduledEventInput Fixtures ─────────────────────────────────────

/**
 * Minimal create input containing only mandatory user-editable fields.
 * Optional fields (description, expectedLoad, priority) are omitted.
 */
export const CREATE_FIXTURE_MINIMAL: CreateScheduledEventInput = {
  eventName: "Orientation Week Schedule Release",
  eventType: "OTHER",
  startTime: "2026-11-10T08:00:00Z",
  endTime: "2026-11-10T12:00:00Z",
  prewarmWindowMinutes: 15,
};

/**
 * Create input with all optional fields populated.
 */
export const CREATE_FIXTURE_WITH_OPTIONAL: CreateScheduledEventInput = {
  eventName: "Mid-Term Makeup Examination Registration",
  eventType: "REGISTRATION",
  description:
    "Special registration session for verified medical and athletic exemptions.",
  startTime: "2026-11-18T09:00:00+05:30",
  endTime: "2026-11-19T17:00:00+05:30",
  expectedLoad: "MEDIUM",
  priority: "MEDIUM",
  prewarmWindowMinutes: 30,
};

/**
 * High-priority result release create input.
 */
export const CREATE_FIXTURE_RESULT_RELEASE: CreateScheduledEventInput = {
  eventName: "Faculty of Engineering Final Year Results Release",
  eventType: "RESULT_RELEASE",
  description:
    "Graduating cohort degree classification and final transcript publication.",
  startTime: "2026-12-01T08:30:00+05:30",
  endTime: "2026-12-01T17:30:00+05:30",
  expectedLoad: "VERY_HIGH",
  priority: "CRITICAL",
  prewarmWindowMinutes: 60,
};

/**
 * Course registration create input featuring an extended prewarm window.
 */
export const CREATE_FIXTURE_REGISTRATION_ALT_PREWARM: CreateScheduledEventInput = {
  eventName: "Hostel Accommodation Booking Window",
  eventType: "REGISTRATION",
  description:
    "Residential hall room selection for incoming first-year undergraduate students.",
  startTime: "2026-12-10T07:00:00Z",
  endTime: "2026-12-11T20:00:00Z",
  expectedLoad: "HIGH",
  priority: "HIGH",
  prewarmWindowMinutes: 120,
};

/**
 * Canonical collection of valid CreateScheduledEventInput fixtures.
 */
export const SAMPLE_CREATE_EVENT_INPUTS: readonly CreateScheduledEventInput[] = [
  CREATE_FIXTURE_MINIMAL,
  CREATE_FIXTURE_WITH_OPTIONAL,
  CREATE_FIXTURE_RESULT_RELEASE,
  CREATE_FIXTURE_REGISTRATION_ALT_PREWARM,
] as const;

// ── 3. Intentionally Invalid Test Cases ───────────────────────────────────────
//
// These objects are purposefully malformed to test validation rejection in schemas,
// API route handlers, and error handlers. They are typed as unknown / Record<string, unknown>
// and strictly isolated from the valid collections above.
// ─────────────────────────────────────────────────────────────────────────────

export interface InvalidTestCase {
  caseId: string;
  scenario: string;
  targetSchema: "ScheduledEventSchema" | "CreateScheduledEventInputSchema" | "UpdateScheduledEventInputSchema";
  payload: unknown;
  expectedIssueField?: string;
  expectedIssueCode?: string;
}

export const INVALID_FIXTURES: readonly InvalidTestCase[] = [
  {
    caseId: "INV-001",
    scenario: "Missing required event name",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventType: "RESULT_RELEASE",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueField: "eventName",
  },
  {
    caseId: "INV-002",
    scenario: "Empty or whitespace-only event name",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "    ",
      eventType: "RESULT_RELEASE",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueField: "eventName",
  },
  {
    caseId: "INV-003",
    scenario: "Invalid event type not in enum",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "Invalid Type Event",
      eventType: "UNRECOGNIZED_TYPE_NAME",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueField: "eventType",
  },
  {
    caseId: "INV-004",
    scenario: "Datetime missing timezone information",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "No Timezone Event",
      eventType: "OTHER",
      startTime: "2026-11-15T08:00:00",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueField: "startTime",
  },
  {
    caseId: "INV-005",
    scenario: "Malformed timezone offset (+99:99)",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "Malformed Offset Event",
      eventType: "OTHER",
      startTime: "2026-11-15T08:00:00+99:99",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueField: "startTime",
  },
  {
    caseId: "INV-006",
    scenario: "endTime earlier than startTime",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "Reversed Dates Event",
      eventType: "FLASH_SALE",
      startTime: "2026-11-15T18:00:00Z",
      endTime: "2026-11-15T08:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueField: "endTime",
  },
  {
    caseId: "INV-007",
    scenario: "Negative prewarm window minutes",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "Negative Prewarm Event",
      eventType: "OTHER",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: -15,
    },
    expectedIssueField: "prewarmWindowMinutes",
  },
  {
    caseId: "INV-008",
    scenario: "Prewarm window exceeding maximum allowable limit (10080 minutes / 7 days)",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "Excessive Prewarm Event",
      eventType: "OTHER",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 15000,
    },
    expectedIssueField: "prewarmWindowMinutes",
  },
  {
    caseId: "INV-009",
    scenario: "Client attempting to inject system-managed eventId on creation",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventId: "EVT-UNAUTHORIZED-001",
      eventName: "Injected System ID Event",
      eventType: "OTHER",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueCode: "unrecognized_keys",
  },
  {
    caseId: "INV-010",
    scenario: "Client attempting to set system-managed status on creation",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      status: "COMPLETED",
      eventName: "Injected Status Event",
      eventType: "OTHER",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
    },
    expectedIssueCode: "unrecognized_keys",
  },
  {
    caseId: "INV-011",
    scenario: "Empty update payload (no fields provided)",
    targetSchema: "UpdateScheduledEventInputSchema",
    payload: {},
  },
  {
    caseId: "INV-012",
    scenario: "Update payload with endTime earlier than startTime",
    targetSchema: "UpdateScheduledEventInputSchema",
    payload: {
      startTime: "2026-11-15T18:00:00Z",
      endTime: "2026-11-15T08:00:00Z",
    },
    expectedIssueField: "endTime",
  },
  {
    caseId: "INV-013",
    scenario: "Client-supplied unknown property on creation",
    targetSchema: "CreateScheduledEventInputSchema",
    payload: {
      eventName: "Unknown Property Event",
      eventType: "OTHER",
      startTime: "2026-11-15T08:00:00Z",
      endTime: "2026-11-15T18:00:00Z",
      prewarmWindowMinutes: 30,
      maliciousFlag: true,
    },
    expectedIssueCode: "unrecognized_keys",
  },
] as const;
