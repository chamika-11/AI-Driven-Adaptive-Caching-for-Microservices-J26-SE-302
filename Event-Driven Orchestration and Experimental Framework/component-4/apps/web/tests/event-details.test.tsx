// ─────────────────────────────────────────────────────────────────────────────
// Event Details and Lifecycle Actions Tests (Part 3.4) — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Verifies Event Details view rendering, timezone formatting, lifecycle action
// availability, cancellation confirmation, deletion confirmation, and error states.
// ─────────────────────────────────────────────────────────────────────────────

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { App } from "../src/App.js";
import { EventDetailsModal } from "../src/components/dashboard/EventDetailsModal.js";
import {
  FIXTURE_RESULT_RELEASE,
  FIXTURE_COMPLETED_EVENT,
  FIXTURE_PROCESSING_EVENT,
  FIXTURE_CANCELLED_EVENT,
  type ScheduledEvent,
} from "@component4/shared";

describe("Part 3.4 — Event Details and Lifecycle Actions", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  // ── 1. Event Details View ───────────────────────────────────────────────────

  describe("1. Event Details View Rendering", () => {
    it("renders all supported event fields including eventId, name, type, timing, priority, prewarm, and audit timestamps", async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string | URL) => {
        const urlStr = String(url);
        if (urlStr.includes(`/api/events/${FIXTURE_RESULT_RELEASE.eventId}`)) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.reject(new Error(`Unhandled URL: ${urlStr}`));
      });

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      // Verify loading state appears first
      expect(screen.getByText(/Fetching event specification/i)).toBeInTheDocument();

      // Wait for details to populate
      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // 1. Event ID (verified without internal MongoDB _id or __v)
      expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventId)).toBeInTheDocument();
      expect(screen.queryByText(/_id/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/__v/i)).not.toBeInTheDocument();

      // 2. Classification / Type
      expect(screen.getByText("RESULT RELEASE")).toBeInTheDocument();

      // 3. Description
      expect(screen.getByText(FIXTURE_RESULT_RELEASE.description!)).toBeInTheDocument();

      // 4. Prewarm Window
      expect(screen.getByText(/60 minutes/i)).toBeInTheDocument();

      // 5. Lifecycle Status
      expect(screen.getAllByText("SCHEDULED").length).toBeGreaterThan(0);

      // 6. Expected Load & Priority
      expect(screen.getByText("VERY_HIGH")).toBeInTheDocument();
      expect(screen.getByText("CRITICAL")).toBeInTheDocument();

      // 7. Timezone information banner
      expect(screen.getByText(/Timestamp transparency: Times displayed in/i)).toBeInTheDocument();

      // 8. Audit timestamps section
      expect(screen.getByText(/Record Created:/i)).toBeInTheDocument();
      expect(screen.getByText(/Last Modified:/i)).toBeInTheDocument();
    });

    it("displays optional fields gracefully when absent", async () => {
      const minimalEvent: ScheduledEvent = {
        eventId: "EVT-MINIMAL-001",
        eventName: "Faculty General Assembly",
        eventType: "OTHER",
        startTime: "2026-11-20T10:00:00Z",
        endTime: "2026-11-20T12:00:00Z",
        prewarmWindowMinutes: 0,
        status: "SCHEDULED",
        createdAt: "2026-10-15T08:00:00Z",
        updatedAt: "2026-10-15T08:00:00Z",
        // description, expectedLoad, and priority intentionally omitted
      };

      globalThis.fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ event: minimalEvent }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

      render(
        <EventDetailsModal
          isOpen={true}
          eventId="EVT-MINIMAL-001"
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText("Faculty General Assembly")).toBeInTheDocument();
      });

      // Graceful fallback for empty description
      expect(screen.getByText("No detailed description was provided.")).toBeInTheDocument();

      // Optional load and priority render fallback badges
      expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    });

    it("handles not-found (404) responses gracefully with user-friendly message and return action", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            statusCode: 404,
            message: "Scheduled event with ID 'EVT-NON-EXISTENT' was not found",
          }),
          { status: 404, headers: { "Content-Type": "application/json" } }
        )
      );

      const handleClose = vi.fn();

      render(
        <EventDetailsModal
          isOpen={true}
          eventId="EVT-NON-EXISTENT"
          onClose={handleClose}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/Event Not Found/i)).toBeInTheDocument();
      });

      expect(
        screen.getByText(/The requested event with identifier 'EVT-NON-EXISTENT' could not be found/i)
      ).toBeInTheDocument();

      // Return button triggers onClose
      const returnBtn = screen.getByRole("button", { name: /Return to Events Dashboard/i });
      fireEvent.click(returnBtn);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it("displays error banner with retry option when network request fails", async () => {
      let failCount = 1;
      globalThis.fetch = vi.fn().mockImplementation(() => {
        if (failCount > 0) {
          failCount--;
          return Promise.resolve(
            new Response(
              JSON.stringify({ statusCode: 500, message: "Database connection timed out" }),
              { status: 500, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      });

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/Database connection timed out/i)).toBeInTheDocument();
      });

      // Click retry
      const retryBtn = screen.getByRole("button", { name: /Retry Request|Retry/i });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });
    });

    it("invokes onEdit when user clicks Edit Event from details view", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

      const handleEdit = vi.fn();

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={handleEdit}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      const editBtn = screen.getByRole("button", { name: `Edit ${FIXTURE_RESULT_RELEASE.eventName}` });
      fireEvent.click(editBtn);

      expect(handleEdit).toHaveBeenCalledTimes(1);
      expect(handleEdit).toHaveBeenCalledWith(FIXTURE_RESULT_RELEASE);
    });
  });

  // ── 2. Lifecycle Actions & Cancellation ─────────────────────────────────────

  describe("2. Event Cancellation Lifecycle Action", () => {
    it("enables Cancel Event only for SCHEDULED events and disables it for COMPLETED or PROCESSING events", async () => {
      // Test 1: SCHEDULED event -> Cancel is enabled
      globalThis.fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ event: FIXTURE_RESULT_RELEASE }), // SCHEDULED
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

      const { unmount } = render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      const cancelBtn = screen.getByRole("button", {
        name: `Cancel scheduled event ${FIXTURE_RESULT_RELEASE.eventName}`,
      });
      expect(cancelBtn).not.toBeDisabled();
      unmount();

      // Test 2: COMPLETED event -> Cancel is disabled
      globalThis.fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ event: FIXTURE_COMPLETED_EVENT }), // COMPLETED
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

      const { unmount: unmount2 } = render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_COMPLETED_EVENT.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_COMPLETED_EVENT.eventName)).toBeInTheDocument();
      });

      const completedCancelBtn = screen.getByRole("button", {
        name: `Cancel scheduled event ${FIXTURE_COMPLETED_EVENT.eventName}`,
      });
      expect(completedCancelBtn).toBeDisabled();
      expect(completedCancelBtn.getAttribute("title")).toContain("only permitted for SCHEDULED events");
      unmount2();

      // Test 3: PROCESSING event -> Cancel is disabled
      globalThis.fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ event: FIXTURE_PROCESSING_EVENT }), // PROCESSING
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_PROCESSING_EVENT.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_PROCESSING_EVENT.eventName)).toBeInTheDocument();
      });

      const processingCancelBtn = screen.getByRole("button", {
        name: `Cancel scheduled event ${FIXTURE_PROCESSING_EVENT.eventName}`,
      });
      expect(processingCancelBtn).toBeDisabled();
    });

    it("displays confirmation dialog with event details and does not call API when dismissed", async () => {
      const fetchMock = vi.fn().mockImplementation((url: string | URL) => {
        const urlStr = String(url);
        if (urlStr.includes(`/api/events/${FIXTURE_RESULT_RELEASE.eventId}`)) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.reject(new Error(`Unexpected URL: ${urlStr}`));
      });
      globalThis.fetch = fetchMock;

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Click Cancel Event
      const cancelBtn = screen.getByRole("button", {
        name: `Cancel scheduled event ${FIXTURE_RESULT_RELEASE.eventName}`,
      });
      fireEvent.click(cancelBtn);

      // Verify confirmation dialog displays event name and ID
      const confirmDialog = screen.getByRole("dialog", { name: /Cancel Scheduled Event\?/i });
      expect(confirmDialog).toBeInTheDocument();
      expect(
        within(confirmDialog).getByText(new RegExp(FIXTURE_RESULT_RELEASE.eventName, "i"))
      ).toBeInTheDocument();
      expect(
        within(confirmDialog).getByText(new RegExp(FIXTURE_RESULT_RELEASE.eventId, "i"))
      ).toBeInTheDocument();

      // Click Dismiss / Keep Scheduled
      const dismissBtn = screen.getByRole("button", { name: /Keep Scheduled/i });
      fireEvent.click(dismissBtn);

      // Confirm dialog closed
      expect(screen.queryByText(/Cancel Scheduled Event\?/i)).not.toBeInTheDocument();

      // Verify no cancellation POST API request was made
      const postCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes("/cancel"));
      expect(postCalls.length).toBe(0);
    });

    it("submits POST /api/events/:eventId/cancel on confirmation and updates status", async () => {
      const cancelledEvent: ScheduledEvent = {
        ...FIXTURE_RESULT_RELEASE,
        status: "CANCELLED",
        updatedAt: new Date().toISOString(),
      };

      const fetchMock = vi.fn().mockImplementation((url: string | URL, opts?: RequestInit) => {
        const urlStr = String(url);
        if (urlStr.endsWith("/cancel") && opts?.method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: cancelledEvent }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        if (urlStr.includes(`/api/events/${FIXTURE_RESULT_RELEASE.eventId}`)) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.reject(new Error(`Unexpected URL: ${urlStr}`));
      });
      globalThis.fetch = fetchMock;

      const handleCancelled = vi.fn();

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={handleCancelled}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Open cancel dialog
      const cancelBtn = screen.getByRole("button", {
        name: `Cancel scheduled event ${FIXTURE_RESULT_RELEASE.eventName}`,
      });
      fireEvent.click(cancelBtn);

      // Confirm cancellation
      const confirmBtn = screen.getByRole("button", { name: /Yes, Cancel Event/i });
      fireEvent.click(confirmBtn);

      // Verify callback triggered with updated cancelled event
      await waitFor(() => {
        expect(handleCancelled).toHaveBeenCalledWith(cancelledEvent);
      });

      // Confirmation dialog closes and details view now displays CANCELLED
      expect(screen.queryByText(/Cancel Scheduled Event\?/i)).not.toBeInTheDocument();
      expect(screen.getByText(/This event is CANCELLED\./i)).toBeInTheDocument();
    });

    it("handles cancellation failure safely, displaying error and keeping confirmation dialog open", async () => {
      const fetchMock = vi.fn().mockImplementation((url: string | URL, opts?: RequestInit) => {
        const urlStr = String(url);
        if (urlStr.endsWith("/cancel") && opts?.method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                statusCode: 409,
                message: "Cannot cancel event because it is already COMPLETED",
              }),
              { status: 409, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        if (urlStr.includes(`/api/events/${FIXTURE_RESULT_RELEASE.eventId}`)) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.reject(new Error(`Unexpected URL: ${urlStr}`));
      });
      globalThis.fetch = fetchMock;

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Open cancel dialog
      fireEvent.click(
        screen.getByRole("button", {
          name: `Cancel scheduled event ${FIXTURE_RESULT_RELEASE.eventName}`,
        })
      );

      // Confirm
      fireEvent.click(screen.getByRole("button", { name: /Yes, Cancel Event/i }));

      // Dialog stays open and shows error
      await waitFor(() => {
        expect(
          screen.getByText(/Cannot cancel event because it is already COMPLETED/i)
        ).toBeInTheDocument();
      });
      expect(screen.getByText(/Cancel Scheduled Event\?/i)).toBeInTheDocument();
    });
  });

  // ── 3. Deletion Action ──────────────────────────────────────────────────────

  describe("3. Event Deletion Action", () => {
    it("prompts with confirmation warning of permanent irreversible deletion", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={vi.fn()}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={vi.fn()}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Click Delete
      fireEvent.click(
        screen.getByRole("button", {
          name: `Delete event ${FIXTURE_RESULT_RELEASE.eventName}`,
        })
      );

      // Verify destructive confirmation dialog
      expect(screen.getByText(/Permanently Delete Event\?/i)).toBeInTheDocument();
      expect(screen.getByText(/action is permanent and irreversible/i)).toBeInTheDocument();

      // Dismiss dialog
      fireEvent.click(screen.getByRole("button", { name: /Keep Event/i }));
      expect(screen.queryByText(/Permanently Delete Event\?/i)).not.toBeInTheDocument();
    });

    it("submits DELETE /api/events/:eventId on confirmation, triggers onEventDeleted, and closes modal", async () => {
      const fetchMock = vi.fn().mockImplementation((url: string | URL, opts?: RequestInit) => {
        const urlStr = String(url);
        if (opts?.method === "DELETE") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                success: true,
                message: "Scheduled event was deleted successfully",
                eventId: FIXTURE_RESULT_RELEASE.eventId,
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        if (urlStr.includes(`/api/events/${FIXTURE_RESULT_RELEASE.eventId}`)) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.reject(new Error(`Unexpected URL: ${urlStr}`));
      });
      globalThis.fetch = fetchMock;

      const handleDeleted = vi.fn();
      const handleClose = vi.fn();

      render(
        <EventDetailsModal
          isOpen={true}
          eventId={FIXTURE_RESULT_RELEASE.eventId}
          onClose={handleClose}
          onEdit={vi.fn()}
          onEventCancelled={vi.fn()}
          onEventDeleted={handleDeleted}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Open Delete modal
      fireEvent.click(
        screen.getByRole("button", {
          name: `Delete event ${FIXTURE_RESULT_RELEASE.eventName}`,
        })
      );

      // Confirm delete
      fireEvent.click(screen.getByRole("button", { name: /Yes, Delete Event/i }));

      await waitFor(() => {
        expect(handleDeleted).toHaveBeenCalledWith(
          FIXTURE_RESULT_RELEASE.eventId,
          FIXTURE_RESULT_RELEASE.eventName
        );
      });

      expect(handleClose).toHaveBeenCalled();
    });
  });

  // ── 4. Dashboard Integration ───────────────────────────────────────────────

  describe("4. Dashboard Integration & Table Interaction", () => {
    it("opens the details modal when clicking View action button in the events table", async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string | URL) => {
        const urlStr = String(url);

        if (urlStr.includes("/api/health/ready")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ status: "ok", database: "connected" }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        if (urlStr.includes(`/api/events/${FIXTURE_RESULT_RELEASE.eventId}`)) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        if (urlStr.includes("/api/events")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                events: [FIXTURE_RESULT_RELEASE],
                pagination: { total: 1, page: 1, limit: 10, totalPages: 1 },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        return Promise.reject(new Error(`Unexpected URL: ${urlStr}`));
      });

      render(<App />);

      // Wait for table to load
      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Click "View" action button
      const viewBtn = screen.getByRole("button", {
        name: `View details for ${FIXTURE_RESULT_RELEASE.eventName}`,
      });
      fireEvent.click(viewBtn);

      // Verify details modal opened
      await waitFor(() => {
        expect(screen.getByRole("dialog", { name: /Semester 1 Examination Results Release/i })).toBeInTheDocument();
      });

      expect(screen.getByText(/Application Event ID:/i)).toBeInTheDocument();
    });

    it("opens the details modal when clicking the event name link in the table", async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string | URL) => {
        const urlStr = String(url);

        if (urlStr.includes("/api/health/ready")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ status: "ok", database: "connected" }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        if (urlStr.includes(`/api/events/${FIXTURE_RESULT_RELEASE.eventId}`)) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ event: FIXTURE_RESULT_RELEASE }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        if (urlStr.includes("/api/events")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                events: [FIXTURE_RESULT_RELEASE],
                pagination: { total: 1, page: 1, limit: 10, totalPages: 1 },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        return Promise.reject(new Error(`Unexpected URL: ${urlStr}`));
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      });

      // Click the clickable event name link in the table
      const nameLink = screen.getByRole("button", {
        name: FIXTURE_RESULT_RELEASE.eventName,
      });
      fireEvent.click(nameLink);

      // Verify details dialog is open
      await waitFor(() => {
        expect(screen.getByText(/Schedule & Timing/i)).toBeInTheDocument();
      });
    });
  });
});
