// ─────────────────────────────────────────────────────────────────────────────
// Event Management API Service — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Communicates with backend endpoints (/api/events, /api/health/ready).
// ─────────────────────────────────────────────────────────────────────────────

import type {
  ScheduledEvent,
  CreateScheduledEventInput,
  UpdateScheduledEventInput,
  EventResponse,
  EventListResponse,
  ListEventsQuery,
  HealthCheckResponse,
} from "@component4/shared";
import { apiRequest } from "./api.client.js";

export interface EventSummaryCounts {
  total: number;
  scheduled: number;
  processing: number;
  completed: number;
  cancelled: number;
}

/**
 * Serializes query parameters into URL search string.
 */
function buildQueryString(query: ListEventsQuery = {}): string {
  const params = new URLSearchParams();

  if (query.page !== undefined) params.set("page", String(query.page));
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.status) params.set("status", query.status);
  if (query.eventType) params.set("eventType", query.eventType);
  if (query.priority) params.set("priority", query.priority);
  if (query.expectedLoad) params.set("expectedLoad", query.expectedLoad);
  if (query.startDateFrom) params.set("startDateFrom", query.startDateFrom);
  if (query.startDateTo) params.set("startDateTo", query.startDateTo);
  if (query.sortBy) params.set("sortBy", query.sortBy);
  if (query.sortOrder) params.set("sortOrder", query.sortOrder);

  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Fetches scheduled events with optional filtering, sorting, and pagination.
 */
export async function getEvents(
  query: ListEventsQuery = {},
  signal?: AbortSignal
): Promise<EventListResponse> {
  const queryString = buildQueryString(query);
  return apiRequest<EventListResponse>(`/api/events${queryString}`, { signal });
}

/**
 * Fetches accurate server-side summary counts across lifecycle statuses.
 * Queries status counts in parallel using lightweight limit=1 queries to get exact totals.
 */
export async function getEventSummaryCounts(
  signal?: AbortSignal
): Promise<EventSummaryCounts> {
  try {
    const [allRes, schedRes, procRes, compRes, cancRes] = await Promise.all([
      getEvents({ limit: 1 }, signal),
      getEvents({ status: "SCHEDULED", limit: 1 }, signal),
      getEvents({ status: "PROCESSING", limit: 1 }, signal),
      getEvents({ status: "COMPLETED", limit: 1 }, signal),
      getEvents({ status: "CANCELLED", limit: 1 }, signal),
    ]);

    return {
      total: allRes.pagination.total,
      scheduled: schedRes.pagination.total,
      processing: procRes.pagination.total,
      completed: compRes.pagination.total,
      cancelled: cancRes.pagination.total,
    };
  } catch (error) {
    if (
      (error instanceof Error && error.name === "AbortError") ||
      (typeof DOMException !== "undefined" &&
        error instanceof DOMException &&
        error.name === "AbortError")
    ) {
      throw error;
    }
    // Return empty counts if counts query encounters an error
    return {
      total: 0,
      scheduled: 0,
      processing: 0,
      completed: 0,
      cancelled: 0,
    };
  }
}

/**
 * Checks API server and database readiness (/api/health/ready).
 */
export async function getSystemReadiness(
  signal?: AbortSignal
): Promise<HealthCheckResponse & { database?: string }> {
  return apiRequest<HealthCheckResponse & { database?: string }>(
    "/api/health/ready",
    { signal }
  );
}

/**
 * Creates a new scheduled business event via POST /api/events.
 */
export async function createEvent(
  input: CreateScheduledEventInput,
  signal?: AbortSignal
): Promise<ScheduledEvent> {
  const res = await apiRequest<EventResponse>("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });
  return res.event;
}

/**
 * Retrieves a single scheduled event by its application-level eventId.
 */
export async function getEventById(
  eventId: string,
  signal?: AbortSignal
): Promise<ScheduledEvent> {
  const res = await apiRequest<EventResponse>(
    `/api/events/${encodeURIComponent(eventId)}`,
    { signal }
  );
  return res.event;
}

/**
 * Partially updates an existing scheduled event via PATCH /api/events/:eventId.
 */
export async function updateEvent(
  eventId: string,
  input: UpdateScheduledEventInput,
  signal?: AbortSignal
): Promise<ScheduledEvent> {
  const res = await apiRequest<EventResponse>(
    `/api/events/${encodeURIComponent(eventId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal,
    }
  );
  return res.event;
}

/**
 * Cancels a scheduled event via POST /api/events/:eventId/cancel.
 * Enforces lifecycle transition: only SCHEDULED events may be cancelled.
 */
export async function cancelEvent(
  eventId: string,
  signal?: AbortSignal
): Promise<ScheduledEvent> {
  const res = await apiRequest<EventResponse>(
    `/api/events/${encodeURIComponent(eventId)}/cancel`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
    }
  );
  return res.event;
}

/**
 * Permanently deletes a scheduled event via DELETE /api/events/:eventId.
 */
export async function deleteEvent(
  eventId: string,
  signal?: AbortSignal
): Promise<{ success: boolean; message: string; eventId: string }> {
  return apiRequest<{ success: boolean; message: string; eventId: string }>(
    `/api/events/${encodeURIComponent(eventId)}`,
    {
      method: "DELETE",
      signal,
    }
  );
}

