import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within, act } from "@testing-library/react";
import { App } from "../src/App.js";
import {
  FIXTURE_RESULT_RELEASE,
  FIXTURE_REGISTRATION_OPENING,
} from "@component4/shared";

describe("Frontend Dashboard Foundation — Part 3.2", () => {
  const sampleEvents = [
    FIXTURE_RESULT_RELEASE,
    FIXTURE_REGISTRATION_OPENING,
  ];

  function createFetchMock(options?: {
    eventsFail?: boolean;
    healthFail?: boolean;
    emptyEvents?: boolean;
    customEvents?: typeof sampleEvents;
    invalidJson?: boolean;
  }) {
    return vi.fn().mockImplementation((url: string | URL) => {
      const urlString = String(url);

      // System Health Readiness Endpoint
      if (urlString.includes("/api/health/ready")) {
        if (options?.healthFail) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ status: "error", message: "Database down" }),
              { status: 503, headers: { "Content-Type": "application/json" } }
            )
          );
        }
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

      // Event List and Summary Counts Endpoint
      if (urlString.includes("/api/events")) {
        if (options?.eventsFail) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                message: "Failed to connect to MongoDB cluster",
                statusCode: 500,
              }),
              { status: 500, headers: { "Content-Type": "application/json" } }
            )
          );
        }

        if (options?.invalidJson) {
          return Promise.resolve(
            new Response("Internal Server Error HTML trace", {
              status: 500,
              headers: { "Content-Type": "text/html" },
            })
          );
        }

        const parsedUrl = new URL(urlString, "http://localhost:3000");
        const statusParam = parsedUrl.searchParams.get("status");
        const limitParam = parsedUrl.searchParams.get("limit");
        const pageParam = Number(parsedUrl.searchParams.get("page") || "1");

        // Summary count queries (limit=1)
        if (limitParam === "1") {
          let count = 20;
          if (options?.emptyEvents) count = 0;
          else if (statusParam === "SCHEDULED") count = 12;
          else if (statusParam === "PROCESSING") count = 1;
          else if (statusParam === "COMPLETED") count = 5;
          else if (statusParam === "CANCELLED") count = 2;

          return Promise.resolve(
            new Response(
              JSON.stringify({
                events: count > 0 ? [sampleEvents[0]] : [],
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

        // Normal event list response
        const eventsToReturn = options?.emptyEvents
          ? []
          : (options?.customEvents ?? sampleEvents);

        return Promise.resolve(
          new Response(
            JSON.stringify({
              events: eventsToReturn,
              pagination: {
                total: options?.emptyEvents ? 0 : 20,
                page: pageParam,
                limit: 10,
                totalPages: options?.emptyEvents ? 0 : 2,
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      return Promise.reject(new Error(`Unhandled URL: ${urlString}`));
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── Scenario 1: Main layout and navigation ────────────────────────────────
  it("renders the main layout, sidebar, header, and system readiness", async () => {
    global.fetch = createFetchMock();

    render(<App />);

    // Brand and Navigation Links in Sidebar
    expect(screen.getByText("Event Intelligence")).toBeInTheDocument();
    expect(screen.getByText(/adaptive cache/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^dashboard$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^events$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /api documentation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /settings/i })).toBeInTheDocument();

    // Header Content
    expect(screen.getByRole("heading", { level: 2, name: /event intelligence dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh dashboard events/i })).toBeInTheDocument();

    // System Readiness status badge
    await waitFor(() => {
      expect(screen.getByText(/api online/i)).toBeInTheDocument();
    });
  });

  // ── Scenario 2: Loading state while API request is pending ────────────────
  it("displays an accessible loading spinner while the API request is pending", async () => {
    let resolveEvents: (value: Response) => void;
    const pendingPromise = new Promise<Response>((resolve) => {
      resolveEvents = resolve;
    });

    global.fetch = vi.fn().mockImplementation((url: string | URL) => {
      const urlString = String(url);
      if (urlString.includes("/api/health/ready")) {
        return Promise.resolve(
          new Response(JSON.stringify({ status: "ok" }), { status: 200 })
        );
      }
      return pendingPromise;
    });

    render(<App />);

    expect(screen.getByText(/fetching events from mongodb atlas/i)).toBeInTheDocument();

    // Resolve promise to clean up
    await act(async () => {
      resolveEvents!(
        new Response(
          JSON.stringify({
            events: [],
            pagination: { total: 0, page: 1, limit: 10, totalPages: 0 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    });
  });

  // ── Scenario 3: Event list renders valid API data ─────────────────────────
  it("renders scheduled events table with accurate columns and formatted values", async () => {
    global.fetch = createFetchMock();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      expect(screen.getByText(FIXTURE_REGISTRATION_OPENING.eventName)).toBeInTheDocument();
    });

    // Verify column headers exist
    expect(screen.getByRole("columnheader", { name: /event details/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /category/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /start time/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /end time/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /priority/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /load/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /prewarm/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /status/i })).toBeInTheDocument();
  });

  // ── Scenario 4: Correct status and priority badges ────────────────────────
  it("displays accurate status and priority badges with accessibility labels", async () => {
    global.fetch = createFetchMock();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
    });

    // Check badges
    const criticalBadges = screen.getAllByText("CRITICAL");
    expect(criticalBadges.length).toBeGreaterThan(0);

    const scheduledBadges = screen.getAllByText("SCHEDULED");
    expect(scheduledBadges.length).toBeGreaterThan(0);

    const loadBadge = screen.getByText("VERY_HIGH");
    expect(loadBadge).toBeInTheDocument();
  });

  // ── Scenario 5: Summary counts calculated from verified data source ───────
  it("displays server-verified summary counts for Total, Scheduled, Completed, and Cancelled", async () => {
    global.fetch = createFetchMock();

    render(<App />);

    await waitFor(() => {
      const cardsSection = screen.getByLabelText(/event summary statistics/i);
      expect(within(cardsSection).getByText("20")).toBeInTheDocument(); // Total
      expect(within(cardsSection).getByText("12")).toBeInTheDocument(); // Scheduled
      expect(within(cardsSection).getByText("5")).toBeInTheDocument();  // Completed
      expect(within(cardsSection).getByText("2")).toBeInTheDocument();  // Cancelled
    });
  });

  // ── Scenario 6: Empty state when API returns zero events ──────────────────
  it("displays an accessible empty state when no events exist", async () => {
    global.fetch = createFetchMock({ emptyEvents: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/no scheduled events found/i)).toBeInTheDocument();
    });
  });

  // ── Scenario 7: Error state appears when API request fails ────────────────
  it("displays error state with user-friendly message when API fails", async () => {
    global.fetch = createFetchMock({ eventsFail: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load events/i)).toBeInTheDocument();
      expect(screen.getByText(/failed to connect to mongodb cluster/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });

  // ── Scenario 8: Retry triggers a new request and recovers ─────────────────
  it("re-fetches dashboard data when Retry button is clicked", async () => {
    let shouldFail = true;
    global.fetch = vi.fn().mockImplementation((url: string | URL) => {
      const urlString = String(url);
      if (urlString.includes("/api/health/ready")) {
        return Promise.resolve(
          new Response(JSON.stringify({ status: "ok", database: "connected" }), { status: 200 })
        );
      }
      if (urlString.includes("/api/events")) {
        if (shouldFail) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ message: "Network connection refused" }),
              { status: 503 }
            )
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              events: sampleEvents,
              pagination: { total: 2, page: 1, limit: 10, totalPages: 1 },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.reject(new Error("Unhandled URL"));
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load events/i)).toBeInTheDocument();
    });

    // Recover on retry
    shouldFail = false;
    const retryBtn = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
    });
  });

  // ── Scenario 9: Search and Filters ────────────────────────────────────────
  it("supports client-side search filtering on loaded events", async () => {
    global.fetch = createFetchMock();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
      expect(screen.getByText(FIXTURE_REGISTRATION_OPENING.eventName)).toBeInTheDocument();
    });

    const searchInput = screen.getByLabelText(/search events/i);
    fireEvent.change(searchInput, { target: { value: "Examination" } });

    // FIXTURE_RESULT_RELEASE contains "Examination", FIXTURE_REGISTRATION_OPENING does not
    expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
    expect(screen.queryByText(FIXTURE_REGISTRATION_OPENING.eventName)).not.toBeInTheDocument();

    // Verify search notice banner
    expect(screen.getByText(/filtering loaded page for/i)).toBeInTheDocument();

    // Clear filters
    const clearBtn = screen.getByRole("button", { name: /clear filters|reset all search filters/i });
    fireEvent.click(clearBtn);

    expect(screen.getByText(FIXTURE_REGISTRATION_OPENING.eventName)).toBeInTheDocument();
  });

  // ── Scenario 10: Pagination controls ──────────────────────────────────────
  it("renders pagination controls and triggers page change requests", async () => {
    const fetchMock = createFetchMock();
    global.fetch = fetchMock;

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/page 1 of 2/i)).toBeInTheDocument();
    });

    const prevBtn = screen.getByRole("button", { name: /previous page/i });
    const nextBtn = screen.getByRole("button", { name: /next page/i });

    expect(prevBtn).toBeDisabled();
    expect(nextBtn).not.toBeDisabled();

    // Click Next Page
    fireEvent.click(nextBtn);

    await waitFor(() => {
      // Check that a fetch with page=2 was made
      const calls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((url) => url.includes("page=2"))).toBe(true);
    });
  });

  // ── Scenario 11: Invalid/unexpected API response handled safely ───────────
  it("handles non-JSON unexpected responses safely without crashing", async () => {
    global.fetch = createFetchMock({ invalidJson: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load events/i)).toBeInTheDocument();
      expect(screen.getByText(/http error 500/i)).toBeInTheDocument();
    });
  });

  // ── Scenario 12: Refresh updates displayed data ───────────────────────────
  it("reloads dashboard data and re-verifies readiness when Header refresh is clicked", async () => {
    const fetchMock = createFetchMock();
    global.fetch = fetchMock;

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(FIXTURE_RESULT_RELEASE.eventName)).toBeInTheDocument();
    });

    const initialCallCount = fetchMock.mock.calls.length;

    const refreshButton = screen.getByRole("button", { name: /refresh dashboard events/i });
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCallCount);
    });
  });

  // ── Scenario 13: Tab Navigation to Placeholder views ──────────────────────
  it("navigates to API Documentation and Settings placeholder views", async () => {
    global.fetch = createFetchMock();

    render(<App />);

    // Click API Documentation tab
    const apiDocsTab = screen.getByRole("button", { name: /api documentation/i });
    fireEvent.click(apiDocsTab);

    expect(screen.getByRole("heading", { level: 3, name: /api knowledge & openapi ingestion/i })).toBeInTheDocument();
    expect(screen.getByText(/scheduled for part 4.x implementation/i)).toBeInTheDocument();

    // Click Back to Dashboard
    const backBtn = screen.getByRole("button", { name: /return to event dashboard/i });
    fireEvent.click(backBtn);

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 2, name: /event intelligence dashboard/i })).toBeInTheDocument();
    });
  });
});
