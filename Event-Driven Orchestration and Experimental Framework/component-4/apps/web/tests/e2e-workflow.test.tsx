import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { App } from "../src/App.js";
import type { ScheduledEvent } from "@component4/shared";

describe("Part 3.5: Frontend End-to-End Workflow & Integration Tests", () => {
  let mockEvents: ScheduledEvent[];

  const initialEvent: ScheduledEvent = {
    eventId: "evt_e2e_001",
    eventName: "Campus Registration 2026",
    eventType: "REGISTRATION",
    description: "Annual multi-course academic registration",
    startTime: "2026-11-20T08:00:00.000Z",
    endTime: "2026-11-20T18:00:00.000Z",
    expectedLoad: "HIGH",
    priority: "HIGH",
    prewarmWindowMinutes: 45,
    status: "SCHEDULED",
    createdAt: "2026-10-15T00:00:00.000Z",
    updatedAt: "2026-10-15T00:00:00.000Z",
  };

  beforeEach(() => {
    mockEvents = [{ ...initialEvent }];

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string | URL, options?: RequestInit) => {
        const urlStr = String(url);
        const method = options?.method ?? "GET";

        // Health endpoint
        if (urlStr.includes("/api/health/ready")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ status: "ok", database: "connected", timestamp: new Date().toISOString() }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        // Single Event operations (/api/events/:eventId)
        if (urlStr.match(/\/api\/events\/evt_[a-zA-Z0-9_-]+$/)) {
          const match = urlStr.match(/\/api\/events\/(evt_[a-zA-Z0-9_-]+)$/);
          const eventId = match ? match[1] : "";
          const found = mockEvents.find((e) => e.eventId === eventId);

          if (method === "GET") {
            if (!found) {
              return Promise.resolve(
                new Response(JSON.stringify({ error: "Not Found", message: `Event ${eventId} not found` }), {
                  status: 404,
                  headers: { "Content-Type": "application/json" },
                })
              );
            }
            return Promise.resolve(
              new Response(JSON.stringify({ event: found }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
              })
            );
          }

          if (method === "PATCH") {
            if (!found) {
              return Promise.resolve(
                new Response(JSON.stringify({ error: "Not Found", message: `Event ${eventId} not found` }), {
                  status: 404,
                  headers: { "Content-Type": "application/json" },
                })
              );
            }
            const body = JSON.parse(options?.body as string);
            const updated = {
              ...found,
              ...body,
              updatedAt: new Date().toISOString(),
            };
            const idx = mockEvents.findIndex((e) => e.eventId === eventId);
            mockEvents[idx] = updated;
            return Promise.resolve(
              new Response(JSON.stringify({ event: updated }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
              })
            );
          }

          if (method === "DELETE") {
            if (!found) {
              return Promise.resolve(
                new Response(JSON.stringify({ error: "Not Found", message: `Event ${eventId} not found` }), {
                  status: 404,
                  headers: { "Content-Type": "application/json" },
                })
              );
            }
            mockEvents = mockEvents.filter((e) => e.eventId !== eventId);
            return Promise.resolve(
              new Response(JSON.stringify({ success: true, eventId }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
              })
            );
          }
        }

        // Cancellation endpoint (/api/events/:eventId/cancel)
        if (urlStr.match(/\/api\/events\/evt_[a-zA-Z0-9_-]+\/cancel$/)) {
          const match = urlStr.match(/\/api\/events\/(evt_[a-zA-Z0-9_-]+)\/cancel$/);
          const eventId = match ? match[1] : "";
          const found = mockEvents.find((e) => e.eventId === eventId);

          if (!found) {
            return Promise.resolve(
              new Response(JSON.stringify({ error: "Not Found", message: `Event ${eventId} not found` }), {
                status: 404,
                headers: { "Content-Type": "application/json" },
              })
            );
          }

          if (found.status !== "SCHEDULED") {
            return Promise.resolve(
              new Response(
                JSON.stringify({
                  error: "Conflict",
                  message: `Event '${eventId}' cannot be cancelled because its current status is '${found.status}'.`,
                }),
                { status: 409, headers: { "Content-Type": "application/json" } }
              )
            );
          }

          const cancelled: ScheduledEvent = {
            ...found,
            status: "CANCELLED",
            updatedAt: new Date().toISOString(),
          };
          const idx = mockEvents.findIndex((e) => e.eventId === eventId);
          mockEvents[idx] = cancelled;

          return Promise.resolve(
            new Response(JSON.stringify({ event: cancelled }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            })
          );
        }

        // List & Create endpoint (/api/events)
        if (urlStr.includes("/api/events")) {
          if (method === "POST") {
            const body = JSON.parse(options?.body as string);
            const newEvent: ScheduledEvent = {
              ...body,
              eventId: `evt_e2e_${Date.now()}`,
              status: "SCHEDULED",
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            };
            mockEvents.unshift(newEvent);
            return Promise.resolve(
              new Response(JSON.stringify({ event: newEvent }), {
                status: 201,
                headers: { "Content-Type": "application/json" },
              })
            );
          }

          // GET list
          return Promise.resolve(
            new Response(
              JSON.stringify({
                events: mockEvents,
                pagination: {
                  total: mockEvents.length,
                  page: 1,
                  limit: 20,
                  totalPages: Math.ceil(mockEvents.length / 20) || 1,
                },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        return Promise.reject(new Error(`Unhandled URL: ${urlStr}`));
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("Workflow: Inspection -> Details Modal -> Edit Event -> Refresh verified end-to-end", async () => {
    render(<App />);

    // 1. Initial dashboard load
    await waitFor(() => {
      expect(screen.getByText("Campus Registration 2026")).toBeInTheDocument();
    });

    // 2. Open Details Modal by clicking the event name button
    fireEvent.click(screen.getByRole("button", { name: "Campus Registration 2026" }));

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Campus Registration 2026" })).toBeInTheDocument();
    });

    // 3. Verify Details content
    const detailsModal = screen.getByRole("dialog", { name: "Campus Registration 2026" });
    expect(within(detailsModal).getByText("evt_e2e_001")).toBeInTheDocument();
    expect(within(detailsModal).getByText(/45 minutes/i)).toBeInTheDocument();

    // 4. Click "Edit Event" inside Details Modal
    const editBtn = within(detailsModal).getByRole("button", {
      name: "Edit Campus Registration 2026",
    });
    fireEvent.click(editBtn);

    // Details modal closes and Edit modal opens
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Edit Scheduled Event" })).toBeInTheDocument();
    });

    // 5. Change event name
    const editModal = screen.getByRole("dialog", { name: "Edit Scheduled Event" });
    const nameInput = within(editModal).getByLabelText(/Event Name/i);
    fireEvent.change(nameInput, { target: { value: "Campus Registration 2026 (Updated)" } });

    // 6. Submit the form
    const saveBtn = within(editModal).getByRole("button", { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    // 7. Verify modal closes and updated title is reflected in table
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Edit Scheduled Event" })).not.toBeInTheDocument();
      expect(screen.getByText("Campus Registration 2026 (Updated)")).toBeInTheDocument();
    });
  });

  it("Workflow: Inspection -> Cancellation Confirmation -> Status CANCELLED -> Refresh", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Campus Registration 2026")).toBeInTheDocument();
    });

    // Open Details Modal
    fireEvent.click(screen.getByRole("button", { name: "Campus Registration 2026" }));

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Campus Registration 2026" })).toBeInTheDocument();
    });

    const detailsModal = screen.getByRole("dialog", { name: "Campus Registration 2026" });
    const cancelBtn = within(detailsModal).getByRole("button", {
      name: "Cancel scheduled event Campus Registration 2026",
    });
    expect(cancelBtn).not.toBeDisabled();

    // Click Cancel Event -> Confirmation dialog opens
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.getByText(/Cancel Scheduled Event\?/i)).toBeInTheDocument();
    });

    // Confirm Cancellation
    const confirmBtn = screen.getByRole("button", { name: /Yes, Cancel Event/i });
    fireEvent.click(confirmBtn);

    // Confirmation closes, Details refreshed with CANCELLED status badge
    await waitFor(() => {
      expect(screen.queryByText(/Cancel Scheduled Event\?/i)).not.toBeInTheDocument();
    });

    // Cancel button is now disabled inside details modal with tooltip
    await waitFor(() => {
      const refreshedCancelBtn = within(detailsModal).getByRole("button", {
        name: "Cancel scheduled event Campus Registration 2026",
      });
      expect(refreshedCancelBtn).toBeDisabled();
    });
  });

  it("Workflow: Inspection -> Delete Event -> Dismiss -> Re-open -> Confirm -> Removed from Table", async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Campus Registration 2026")).toBeInTheDocument();
    });

    // Open Details Modal
    fireEvent.click(screen.getByRole("button", { name: "Campus Registration 2026" }));

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Campus Registration 2026" })).toBeInTheDocument();
    });

    const detailsModal = screen.getByRole("dialog", { name: "Campus Registration 2026" });
    const deleteBtn = within(detailsModal).getByRole("button", {
      name: "Delete event Campus Registration 2026",
    });

    // Click Delete Event -> Confirmation dialog opens
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByText(/Permanently Delete Event\?/i)).toBeInTheDocument();
    });

    // Dismiss deletion
    const keepBtn = screen.getByRole("button", { name: /Keep Event/i });
    fireEvent.click(keepBtn);

    await waitFor(() => {
      expect(screen.queryByText(/Permanently Delete Event\?/i)).not.toBeInTheDocument();
    });

    // Event still exists in Details modal
    expect(within(detailsModal).getByText("Campus Registration 2026")).toBeInTheDocument();

    // Click Delete Event again
    fireEvent.click(
      within(detailsModal).getByRole("button", {
        name: "Delete event Campus Registration 2026",
      })
    );

    await waitFor(() => {
      expect(screen.getByText(/Permanently Delete Event\?/i)).toBeInTheDocument();
    });

    // Confirm deletion
    const deleteConfirmBtn = screen.getByRole("button", { name: /Yes, Delete Event/i });
    fireEvent.click(deleteConfirmBtn);

    // Both confirmation modal and details modal close, event removed from table
    await waitFor(() => {
      expect(screen.queryByText(/Permanently Delete Event\?/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("dialog", { name: "Campus Registration 2026" })).not.toBeInTheDocument();
      expect(screen.queryByText("Campus Registration 2026")).not.toBeInTheDocument();
    });

    // Empty state rendered
    expect(screen.getByText(/No scheduled events found/i)).toBeInTheDocument();
  });

  it("Workflow: Error Handling -> API 500 displays error banner with Retry trigger", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string | URL) => {
        const urlStr = String(url);
        if (urlStr.includes("/api/health/ready")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ status: "ok", database: "connected", timestamp: new Date().toISOString() }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        if (urlStr.includes("/api/events")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ error: "Internal Server Error", message: "Atlas replica set unreachable" }),
              { status: 500, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        return Promise.reject(new Error("Unknown route"));
      })
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Atlas replica set unreachable")).toBeInTheDocument();
    });

    const retryBtn = screen.getByRole("button", { name: /Retry/i });
    expect(retryBtn).toBeInTheDocument();
  });
});
