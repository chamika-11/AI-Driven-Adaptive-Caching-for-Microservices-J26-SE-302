import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act, within } from "@testing-library/react";
import { App } from "../src/App.js";
import {
  FIXTURE_RESULT_RELEASE,
  FIXTURE_REGISTRATION_OPENING,
  type ScheduledEvent,
  type CreateScheduledEventInput,
  type UpdateScheduledEventInput,
} from "@component4/shared";
import {
  datetimeLocalToIso,
  isoToDatetimeLocal,
  getLocalTimezoneOffset,
  getLocalTimezoneLabel,
} from "../src/utils/date.js";

describe("Part 3.3 — Create and Edit Events", () => {
  let createdEventsStore: ScheduledEvent[] = [];

  function setupFetchMock(customResponses?: {
    createFail?: { status: number; message: string; issues?: string[] };
    updateFail?: { status: number; message: string; issues?: string[] };
    networkError?: boolean;
    onPost?: (body: CreateScheduledEventInput) => void;
    onPatch?: (eventId: string, body: UpdateScheduledEventInput) => void;
  }) {
    createdEventsStore = [
      { ...FIXTURE_RESULT_RELEASE },
      { ...FIXTURE_REGISTRATION_OPENING },
    ];

    return vi.fn().mockImplementation((url: string | URL, init?: RequestInit) => {
      const urlString = String(url);
      const method = init?.method ?? "GET";

      // 1. Health readiness
      if (urlString.includes("/api/health/ready")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              status: "ok",
              component: "Component 4: Event Intelligence",
              version: "0.1.0",
              timestamp: new Date().toISOString(),
              database: "connected",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      // 2. Network error simulation
      if (customResponses?.networkError) {
        return Promise.reject(new Error("Failed to fetch"));
      }

      // 3. POST /api/events (Create Event)
      if (urlString.endsWith("/api/events") && method === "POST") {
        if (customResponses?.createFail) {
          return Promise.resolve(
            new Response(
              JSON.stringify(customResponses.createFail),
              {
                status: customResponses.createFail.status,
                headers: { "Content-Type": "application/json" },
              }
            )
          );
        }

        const body = JSON.parse(String(init?.body)) as CreateScheduledEventInput;
        customResponses?.onPost?.(body);

        const newEvent: ScheduledEvent = {
          eventId: `EVT-NEW-${Date.now()}`,
          eventName: body.eventName,
          eventType: body.eventType,
          description: body.description,
          startTime: body.startTime,
          endTime: body.endTime,
          expectedLoad: body.expectedLoad,
          priority: body.priority,
          prewarmWindowMinutes: body.prewarmWindowMinutes,
          status: "SCHEDULED",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };

        createdEventsStore.unshift(newEvent);

        return Promise.resolve(
          new Response(JSON.stringify({ event: newEvent }), {
            status: 201,
            headers: { "Content-Type": "application/json" },
          })
        );
      }

      // 4. PATCH /api/events/:eventId (Update Event)
      if (urlString.includes("/api/events/") && method === "PATCH") {
        const parts = urlString.split("/");
        const eventId = decodeURIComponent(parts[parts.length - 1]);

        if (customResponses?.updateFail) {
          return Promise.resolve(
            new Response(
              JSON.stringify(customResponses.updateFail),
              {
                status: customResponses.updateFail.status,
                headers: { "Content-Type": "application/json" },
              }
            )
          );
        }

        const body = JSON.parse(String(init?.body)) as UpdateScheduledEventInput;
        customResponses?.onPatch?.(eventId, body);

        const existingIdx = createdEventsStore.findIndex((e) => e.eventId === eventId);
        if (existingIdx === -1) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                error: "Not Found",
                message: `Scheduled event '${eventId}' was not found`,
                statusCode: 404,
              }),
              { status: 404, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        const updated: ScheduledEvent = {
          ...createdEventsStore[existingIdx],
          ...body,
          updatedAt: new Date().toISOString(),
        };
        createdEventsStore[existingIdx] = updated;

        return Promise.resolve(
          new Response(JSON.stringify({ event: updated }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }

      // 5. GET /api/events (List & Summary counts)
      if (urlString.includes("/api/events")) {
        const parsedUrl = new URL(urlString, "http://localhost:3000");
        const limitParam = parsedUrl.searchParams.get("limit");
        const statusParam = parsedUrl.searchParams.get("status");

        if (limitParam === "1") {
          let count = createdEventsStore.length;
          if (statusParam) {
            count = createdEventsStore.filter((e) => e.status === statusParam).length;
          }
          return Promise.resolve(
            new Response(
              JSON.stringify({
                events: count > 0 ? [createdEventsStore[0]] : [],
                pagination: {
                  total: count,
                  page: 1,
                  limit: 1,
                  totalPages: count,
                },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        return Promise.resolve(
          new Response(
            JSON.stringify({
              events: createdEventsStore,
              pagination: {
                total: createdEventsStore.length,
                page: 1,
                limit: 10,
                totalPages: 1,
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      return Promise.reject(new Error(`Unhandled mock request: ${urlString}`));
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ───────────────────────────────────────────────────────────────────────────
  // A. Timezone & Date Conversion Tests (Scenario 21)
  // ───────────────────────────────────────────────────────────────────────────
  describe("Timezone & Date Conversion Utilities", () => {
    it("converts datetime-local value to ISO 8601 with explicit timezone offset", () => {
      const datetimeLocal = "2026-11-20T09:30";
      const iso = datetimeLocalToIso(datetimeLocal);

      expect(iso).toMatch(/^2026-11-20T09:30:00([+-]\d{2}:\d{2}|Z)$/);

      // Verify that parsing the generated ISO produces the exact same local hour and minute
      const parsed = new Date(iso);
      expect(parsed.getFullYear()).toBe(2026);
      expect(parsed.getMonth()).toBe(10); // November (0-indexed)
      expect(parsed.getDate()).toBe(20);
      expect(parsed.getHours()).toBe(9);
      expect(parsed.getMinutes()).toBe(30);
    });

    it("converts ISO 8601 timestamp back to datetime-local string losslessly", () => {
      const datetimeLocal = "2026-12-15T14:45";
      const iso = datetimeLocalToIso(datetimeLocal);
      const convertedBack = isoToDatetimeLocal(iso);

      expect(convertedBack).toBe(datetimeLocal);
    });

    it("handles invalid or empty inputs gracefully", () => {
      expect(datetimeLocalToIso("")).toBe("");
      expect(datetimeLocalToIso("invalid")).toBe("");
      expect(isoToDatetimeLocal("")).toBe("");
      expect(isoToDatetimeLocal("not-a-date")).toBe("");
    });

    it("returns formatted local timezone offset and descriptive label", () => {
      const offset = getLocalTimezoneOffset();
      expect(offset).toMatch(/^([+-]\d{2}:\d{2}|Z)$/);

      const label = getLocalTimezoneLabel();
      expect(typeof label).toBe("string");
      expect(label.length).toBeGreaterThan(0);
    });
  });

  // ───────────────────────────────────────────────────────────────────────────
  // B. Create Event Form Tests (Scenarios 1-12)
  // ───────────────────────────────────────────────────────────────────────────
  describe("Create Event Form", () => {
    it("opens the create modal from the dashboard with empty inputs and default prewarm window", async () => {
      global.fetch = setupFetchMock();
      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      const openBtn = screen.getByRole("button", { name: /create new scheduled event/i });
      fireEvent.click(openBtn);

      const modal = screen.getByRole("dialog", { name: /create scheduled event/i });
      expect(modal).toBeInTheDocument();
      expect(within(modal).getByLabelText(/event name/i)).toHaveValue("");
      expect(within(modal).getByLabelText(/event type/i)).toHaveValue("");
      expect(within(modal).getByLabelText(/prewarm window/i)).toHaveValue(30);
    });

    it("validates required fields on empty submit and displays error messages", async () => {
      global.fetch = setupFetchMock();
      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create new scheduled event/i }));
      const modal = screen.getByRole("dialog");

      // Clear prewarm window to test empty validation
      const prewarmInput = within(modal).getByLabelText(/prewarm window/i);
      fireEvent.change(prewarmInput, { target: { value: "" } });

      const submitBtn = within(modal).getByRole("button", { name: /^create event$/i });
      fireEvent.click(submitBtn);

      expect(within(modal).getByText("Event name is required")).toBeInTheDocument();
      expect(within(modal).getByText("Event type is required")).toBeInTheDocument();
      expect(within(modal).getByText("Start time is required")).toBeInTheDocument();
      expect(within(modal).getByText("End time is required")).toBeInTheDocument();
      expect(within(modal).getByText("Prewarm window must be an integer")).toBeInTheDocument();
    });

    it("rejects invalid prewarm window constraints (negative, non-integer, > 10080)", async () => {
      global.fetch = setupFetchMock();
      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create new scheduled event/i }));
      const modal = screen.getByRole("dialog");

      const prewarmInput = within(modal).getByLabelText(/prewarm window/i);
      const submitBtn = within(modal).getByRole("button", { name: /^create event$/i });

      // Negative
      fireEvent.change(prewarmInput, { target: { value: "-15" } });
      fireEvent.click(submitBtn);
      expect(within(modal).getByText("Prewarm window must be at least 0")).toBeInTheDocument();

      // Non-integer
      fireEvent.change(prewarmInput, { target: { value: "45.5" } });
      fireEvent.click(submitBtn);
      expect(within(modal).getByText("Prewarm window must be an integer")).toBeInTheDocument();

      // Exceeds max 10080
      fireEvent.change(prewarmInput, { target: { value: "15000" } });
      fireEvent.click(submitBtn);
      expect(within(modal).getByText("Prewarm window must not exceed 10080 minutes")).toBeInTheDocument();
    });

    it("rejects end time that is equal to or earlier than start time", async () => {
      global.fetch = setupFetchMock();
      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create new scheduled event/i }));
      const modal = screen.getByRole("dialog");

      fireEvent.change(within(modal).getByLabelText(/event name/i), {
        target: { value: "Valid Event Name" },
      });
      fireEvent.change(within(modal).getByLabelText(/event type/i), {
        target: { value: "RESULT_RELEASE" },
      });
      fireEvent.change(within(modal).getByLabelText(/start date & time/i), {
        target: { value: "2026-11-20T10:00" },
      });
      fireEvent.change(within(modal).getByLabelText(/end date & time/i), {
        target: { value: "2026-11-20T09:00" },
      });

      fireEvent.click(within(modal).getByRole("button", { name: /^create event$/i }));

      expect(within(modal).getByText("End time must be later than start time")).toBeInTheDocument();
    });

    it("submits valid form data, transmits correct ISO payloads, shows success toast, and refreshes dashboard", async () => {
      let capturedPayload: CreateScheduledEventInput | null = null;
      global.fetch = setupFetchMock({
        onPost: (body) => {
          capturedPayload = body;
        },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create new scheduled event/i }));
      const modal = screen.getByRole("dialog");

      // Fill valid values
      fireEvent.change(within(modal).getByLabelText(/event name/i), {
        target: { value: "End Semester Examination 2026" },
      });
      fireEvent.change(within(modal).getByLabelText(/event type/i), {
        target: { value: "REGISTRATION" },
      });
      fireEvent.change(within(modal).getByLabelText(/start date & time/i), {
        target: { value: "2026-11-25T08:00" },
      });
      fireEvent.change(within(modal).getByLabelText(/end date & time/i), {
        target: { value: "2026-11-25T17:00" },
      });
      fireEvent.change(within(modal).getByLabelText(/expected traffic load/i), {
        target: { value: "HIGH" },
      });
      fireEvent.change(within(modal).getByLabelText(/scheduling priority/i), {
        target: { value: "CRITICAL" },
      });
      fireEvent.change(within(modal).getByLabelText(/prewarm window/i), {
        target: { value: "60" },
      });
      fireEvent.change(within(modal).getByLabelText(/description/i), {
        target: { value: "Annual student course enrollment window" },
      });

      await act(async () => {
        fireEvent.click(within(modal).getByRole("button", { name: /^create event$/i }));
      });

      // Verify payload passed to backend
      expect(capturedPayload).not.toBeNull();
      expect(capturedPayload!.eventName).toBe("End Semester Examination 2026");
      expect(capturedPayload!.eventType).toBe("REGISTRATION");
      expect(capturedPayload!.expectedLoad).toBe("HIGH");
      expect(capturedPayload!.priority).toBe("CRITICAL");
      expect(capturedPayload!.prewarmWindowMinutes).toBe(60);
      expect(capturedPayload!.description).toBe("Annual student course enrollment window");
      expect(capturedPayload!.startTime).toMatch(/^2026-11-25T08:00:00/);
      expect(capturedPayload!.endTime).toMatch(/^2026-11-25T17:00:00/);

      // Verify success notification is rendered and modal is closed
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(screen.getByText(/event "end semester examination 2026" was successfully created/i)).toBeInTheDocument();
        expect(screen.getByText("End Semester Examination 2026")).toBeInTheDocument();
      });
    });

    it("displays server validation failure clearly in form banner and preserves entered values", async () => {
      global.fetch = setupFetchMock({
        createFail: {
          status: 400,
          message: "Request validation failed",
          issues: ["eventName: Duplicate event name found in active window"],
        },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create new scheduled event/i }));
      const modal = screen.getByRole("dialog");

      fireEvent.change(within(modal).getByLabelText(/event name/i), {
        target: { value: "Duplicate Exam Event" },
      });
      fireEvent.change(within(modal).getByLabelText(/event type/i), {
        target: { value: "RESULT_RELEASE" },
      });
      fireEvent.change(within(modal).getByLabelText(/start date & time/i), {
        target: { value: "2026-11-20T08:00" },
      });
      fireEvent.change(within(modal).getByLabelText(/end date & time/i), {
        target: { value: "2026-11-20T18:00" },
      });

      await act(async () => {
        fireEvent.click(within(modal).getByRole("button", { name: /^create event$/i }));
      });

      // Check banner and preserved value
      await waitFor(() => {
        expect(within(modal).getByText("Request validation failed")).toBeInTheDocument();
        expect(within(modal).getByText("eventName: Duplicate event name found in active window")).toBeInTheDocument();
        expect(within(modal).getByLabelText(/event name/i)).toHaveValue("Duplicate Exam Event");
      });
    });

    it("handles network failure and preserves user entered values", async () => {
      global.fetch = setupFetchMock({
        networkError: true,
      });

      render(<App />);

      await waitFor(() => {
        // Since health check will fail on initial mount with networkError, error state renders
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create new scheduled event/i }));
      const modal = screen.getByRole("dialog");

      fireEvent.change(within(modal).getByLabelText(/event name/i), {
        target: { value: "Preserved Value Test" },
      });
      fireEvent.change(within(modal).getByLabelText(/event type/i), {
        target: { value: "FLASH_SALE" },
      });
      fireEvent.change(within(modal).getByLabelText(/start date & time/i), {
        target: { value: "2026-11-20T08:00" },
      });
      fireEvent.change(within(modal).getByLabelText(/end date & time/i), {
        target: { value: "2026-11-20T18:00" },
      });

      await act(async () => {
        fireEvent.click(within(modal).getByRole("button", { name: /^create event$/i }));
      });

      await waitFor(() => {
        expect(within(modal).getByText(/unable to connect to the backend api/i)).toBeInTheDocument();
        expect(within(modal).getByLabelText(/event name/i)).toHaveValue("Preserved Value Test");
      });
    });

    it("cancels and closes the form without submitting when Cancel button is clicked", async () => {
      const fetchMock = setupFetchMock();
      global.fetch = fetchMock;

      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create new scheduled event/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /create new scheduled event/i }));
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      const modal = screen.getByRole("dialog");
      const cancelBtn = within(modal).getByRole("button", { name: /cancel/i });
      fireEvent.click(cancelBtn);

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      // No POST request was made
      const calls = fetchMock.mock.calls.map((c) => c[1]?.method);
      expect(calls.includes("POST")).toBe(false);
    });
  });

  // ───────────────────────────────────────────────────────────────────────────
  // C. Edit Event Form Tests (Scenarios 13-20)
  // ───────────────────────────────────────────────────────────────────────────
  describe("Edit Event Form", () => {
    it("opens edit modal with existing event values preloaded", async () => {
      global.fetch = setupFetchMock();
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Click Edit button on the first event row
      const editBtn = screen.getByRole("button", {
        name: new RegExp(`edit ${FIXTURE_RESULT_RELEASE.eventName}`, "i"),
      });
      fireEvent.click(editBtn);

      const modal = screen.getByRole("dialog", { name: /edit scheduled event/i });
      expect(modal).toBeInTheDocument();
      expect(within(modal).getByText(new RegExp(FIXTURE_RESULT_RELEASE.eventId, "i"))).toBeInTheDocument();

      // Check preloaded form inputs
      expect(within(modal).getByLabelText(/event name/i)).toHaveValue(FIXTURE_RESULT_RELEASE.eventName);
      expect(within(modal).getByLabelText(/event type/i)).toHaveValue(FIXTURE_RESULT_RELEASE.eventType);
      expect(within(modal).getByLabelText(/expected traffic load/i)).toHaveValue(FIXTURE_RESULT_RELEASE.expectedLoad);
      expect(within(modal).getByLabelText(/scheduling priority/i)).toHaveValue(FIXTURE_RESULT_RELEASE.priority);
      expect(within(modal).getByLabelText(/prewarm window/i)).toHaveValue(FIXTURE_RESULT_RELEASE.prewarmWindowMinutes);
      expect(within(modal).getByLabelText(/description/i)).toHaveValue(FIXTURE_RESULT_RELEASE.description);
    });

    it("submits partial update with only modified fields and excludes system-managed properties", async () => {
      let patchEventId: string | null = null;
      let patchBody: UpdateScheduledEventInput | null = null;

      global.fetch = setupFetchMock({
        onPatch: (id, body) => {
          patchEventId = id;
          patchBody = body;
        },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      const editBtn = screen.getByRole("button", {
        name: new RegExp(`edit ${FIXTURE_RESULT_RELEASE.eventName}`, "i"),
      });
      fireEvent.click(editBtn);
      const modal = screen.getByRole("dialog");

      // Modify only eventName and priority
      const nameInput = within(modal).getByLabelText(/event name/i);
      fireEvent.change(nameInput, { target: { value: "Updated Examination Name" } });

      const prioritySelect = within(modal).getByLabelText(/scheduling priority/i);
      fireEvent.change(prioritySelect, { target: { value: "HIGH" } });

      await act(async () => {
        fireEvent.click(within(modal).getByRole("button", { name: /save changes/i }));
      });

      expect(patchEventId).toBe(FIXTURE_RESULT_RELEASE.eventId);
      expect(patchBody).not.toBeNull();
      expect(patchBody!.eventName).toBe("Updated Examination Name");
      expect(patchBody!.priority).toBe("HIGH");

      // Verify system-managed fields were NOT sent
      expect((patchBody as Record<string, unknown>)["eventId"]).toBeUndefined();
      expect((patchBody as Record<string, unknown>)["status"]).toBeUndefined();
      expect((patchBody as Record<string, unknown>)["createdAt"]).toBeUndefined();
      expect((patchBody as Record<string, unknown>)["updatedAt"]).toBeUndefined();
      expect((patchBody as Record<string, unknown>)["_id"]).toBeUndefined();

      // Check success toast and refreshed list
      await waitFor(() => {
        expect(screen.getByText(/event "updated examination name" was successfully updated/i)).toBeInTheDocument();
        expect(screen.getByText("Updated Examination Name")).toBeInTheDocument();
      });
    });

    it("rejects an invalid resulting date range when modifying startTime after endTime", async () => {
      global.fetch = setupFetchMock();
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      const editBtn = screen.getByRole("button", {
        name: new RegExp(`edit ${FIXTURE_RESULT_RELEASE.eventName}`, "i"),
      });
      fireEvent.click(editBtn);
      const modal = screen.getByRole("dialog");

      // Set startTime to be way after endTime
      const startInput = within(modal).getByLabelText(/start date & time/i);
      fireEvent.change(startInput, { target: { value: "2026-12-31T23:00" } });

      fireEvent.click(within(modal).getByRole("button", { name: /save changes/i }));

      expect(within(modal).getByText("End time must be later than start time")).toBeInTheDocument();
    });

    it("displays API validation error on update and keeps modal open", async () => {
      global.fetch = setupFetchMock({
        updateFail: {
          status: 400,
          message: "Event update validation failed",
          issues: ["prewarmWindowMinutes: Prewarm window exceeds allowed threshold"],
        },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      const editBtn = screen.getByRole("button", {
        name: new RegExp(`edit ${FIXTURE_RESULT_RELEASE.eventName}`, "i"),
      });
      fireEvent.click(editBtn);
      const modal = screen.getByRole("dialog");

      const nameInput = within(modal).getByLabelText(/event name/i);
      fireEvent.change(nameInput, { target: { value: "Attempted Name" } });

      await act(async () => {
        fireEvent.click(within(modal).getByRole("button", { name: /save changes/i }));
      });

      await waitFor(() => {
        expect(within(modal).getByText("Event update validation failed")).toBeInTheDocument();
        expect(within(modal).getByText("prewarmWindowMinutes: Prewarm window exceeds allowed threshold")).toBeInTheDocument();
        expect(within(modal).getByLabelText(/event name/i)).toHaveValue("Attempted Name");
      });
    });

    it("handles missing event (404 Not Found) gracefully", async () => {
      global.fetch = setupFetchMock({
        updateFail: {
          status: 404,
          message: "Scheduled event with ID 'EVT-MISSING' was not found",
        },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      const editBtn = screen.getByRole("button", {
        name: new RegExp(`edit ${FIXTURE_RESULT_RELEASE.eventName}`, "i"),
      });
      fireEvent.click(editBtn);
      const modal = screen.getByRole("dialog");

      fireEvent.change(within(modal).getByLabelText(/event name/i), {
        target: { value: "Changed Name" },
      });

      await act(async () => {
        fireEvent.click(within(modal).getByRole("button", { name: /save changes/i }));
      });

      await waitFor(() => {
        expect(within(modal).getByText(/scheduled event with id 'evt-missing' was not found/i)).toBeInTheDocument();
      });
    });

    it("cancels edit without submitting changes", async () => {
      const fetchMock = setupFetchMock();
      global.fetch = fetchMock;

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      const editBtn = screen.getByRole("button", {
        name: new RegExp(`edit ${FIXTURE_RESULT_RELEASE.eventName}`, "i"),
      });
      fireEvent.click(editBtn);
      const modal = screen.getByRole("dialog");

      fireEvent.change(within(modal).getByLabelText(/event name/i), {
        target: { value: "Unsaved Name Change" },
      });

      const cancelBtn = within(modal).getByRole("button", { name: /cancel/i });
      fireEvent.click(cancelBtn);

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      const calls = fetchMock.mock.calls.map((c) => c[1]?.method);
      expect(calls.includes("PATCH")).toBe(false);
    });
  });
});
