// ─────────────────────────────────────────────────────────────────────────────
// Dashboard Page Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Primary dashboard view managing event state, summary statistics, search, and pagination.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useCallback, useRef } from "react";
import type {
  ScheduledEvent,
  PaginationMeta,
  ListEventsQuery,
} from "@component4/shared";
import {
  getEvents,
  getEventSummaryCounts,
  type EventSummaryCounts,
} from "../services/events.service.js";
import { SummaryCards } from "../components/dashboard/SummaryCards.js";
import {
  EventFilters,
  type FilterState,
} from "../components/dashboard/EventFilters.js";
import { EventsTable } from "../components/dashboard/EventsTable.js";
import { LoadingSpinner } from "../components/common/LoadingSpinner.js";
import { ErrorState } from "../components/common/ErrorState.js";
import { EventFormModal } from "../components/dashboard/EventFormModal.js";
import { EventDetailsModal } from "../components/dashboard/EventDetailsModal.js";

interface DashboardPageProps {
  refreshTrigger: number;
}

const initialCounts: EventSummaryCounts = {
  total: 0,
  scheduled: 0,
  processing: 0,
  completed: 0,
  cancelled: 0,
};

const initialFilters: FilterState = {
  searchTerm: "",
  status: "",
  eventType: "",
  priority: "",
};

const initialPagination: PaginationMeta = {
  total: 0,
  page: 1,
  limit: 10,
  totalPages: 0,
};

export const DashboardPage: React.FC<DashboardPageProps> = ({
  refreshTrigger,
}) => {
  const [events, setEvents] = useState<ScheduledEvent[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta>(initialPagination);
  const [counts, setCounts] = useState<EventSummaryCounts>(initialCounts);
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Modal and toast state for Create / Edit operations
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [modalMode, setModalMode] = useState<"create" | "edit">("create");
  const [selectedEvent, setSelectedEvent] = useState<ScheduledEvent | null>(null);

  // Details Modal state (Part 3.4)
  const [selectedDetailsEventId, setSelectedDetailsEventId] = useState<string | null>(null);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState<boolean>(false);

  const [successToast, setSuccessToast] = useState<{
    message: string;
    action: "created" | "updated" | "deleted" | "cancelled";
  } | null>(null);

  // Active abort controller reference to prevent stale out-of-order race conditions
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-dismiss success notification after 5 seconds
  useEffect(() => {
    if (!successToast) return;
    const timer = setTimeout(() => {
      setSuccessToast(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [successToast]);

  const isFiltered = Boolean(
    filters.searchTerm || filters.status || filters.eventType || filters.priority
  );

  /**
   * Fetches events and server summary counts.
   */
  const loadDashboardData = useCallback(
    async (pageToLoad = currentPage) => {
      // Cancel previous pending in-flight request if any
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setIsLoading(true);
      setErrorMessage(null);

      try {
        // Build backend query
        const query: ListEventsQuery = {
          page: pageToLoad,
          limit: 10,
          sortBy: "startTime",
          sortOrder: "asc",
        };

        if (filters.status) query.status = filters.status;
        if (filters.eventType) query.eventType = filters.eventType;
        if (filters.priority) query.priority = filters.priority;

        // Fetch events and summary counts concurrently
        const [eventsResponse, countsResponse] = await Promise.all([
          getEvents(query, controller.signal),
          getEventSummaryCounts(controller.signal),
        ]);

        setEvents(eventsResponse.events);
        setPagination(eventsResponse.pagination);
        setCounts(countsResponse);
      } catch (err: unknown) {
        if (
          (err instanceof Error && err.name === "AbortError") ||
          (typeof DOMException !== "undefined" &&
            err instanceof DOMException &&
            err.name === "AbortError")
        ) {
          return; // Ignore aborted requests
        }
        const msg =
          err instanceof Error
            ? err.message
            : "An unexpected error occurred while loading dashboard events";
        setErrorMessage(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [currentPage, filters.status, filters.eventType, filters.priority]
  );

  // Trigger data load when page, filters, or global refreshTrigger changes
  useEffect(() => {
    loadDashboardData(currentPage);

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [loadDashboardData, currentPage, refreshTrigger]);

  const handleFilterChange = (updated: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...updated }));
    setCurrentPage(1); // Reset to first page on filter change
  };

  const handleClearFilters = () => {
    setFilters(initialFilters);
    setCurrentPage(1);
  };

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
  };

  const handleOpenCreate = () => {
    setSelectedEvent(null);
    setModalMode("create");
    setIsModalOpen(true);
  };

  const handleOpenEdit = (event: ScheduledEvent) => {
    setSelectedEvent(event);
    setModalMode("edit");
    setIsModalOpen(true);
  };

  const handleOpenDetails = (event: ScheduledEvent) => {
    setSelectedDetailsEventId(event.eventId);
    setIsDetailsModalOpen(true);
  };

  const handleCloseDetails = () => {
    setIsDetailsModalOpen(false);
    setSelectedDetailsEventId(null);
  };

  const handleEditFromDetails = (event: ScheduledEvent) => {
    // Open edit modal while retaining details context
    setSelectedEvent(event);
    setModalMode("edit");
    setIsModalOpen(true);
  };

  const handleEventCancelled = (event: ScheduledEvent) => {
    setSuccessToast({
      message: `Event "${event.eventName}" was successfully cancelled.`,
      action: "cancelled",
    });
    // Refresh dashboard list and counts
    loadDashboardData(currentPage);
  };

  const handleEventDeleted = (_eventId: string, eventName: string) => {
    setSuccessToast({
      message: `Event "${eventName}" was permanently deleted.`,
      action: "deleted",
    });
    handleCloseDetails();
    // Refresh dashboard list and counts
    loadDashboardData(currentPage);
  };

  const handleModalClose = () => {
    setIsModalOpen(false);
    setSelectedEvent(null);
  };

  const handleMutationSuccess = (
    event: ScheduledEvent,
    action: "created" | "updated"
  ) => {
    setSuccessToast({
      message:
        action === "created"
          ? `Event "${event.eventName}" was successfully created.`
          : `Event "${event.eventName}" was successfully updated.`,
      action,
    });
    // If details modal is open for this event, refresh its ID to trigger re-fetch
    if (selectedDetailsEventId === event.eventId) {
      setSelectedDetailsEventId(event.eventId);
    }
    // Refresh dashboard data
    loadDashboardData(action === "created" ? 1 : currentPage);
  };

  // Client-side text filter on the loaded page records if search term is entered
  const displayedEvents = filters.searchTerm.trim()
    ? events.filter((e) =>
        e.eventName.toLowerCase().includes(filters.searchTerm.trim().toLowerCase())
      )
    : events;

  return (
    <div className="dashboard-page-container">
      {/* 1. Summary Cards Section */}
      <SummaryCards counts={counts} isLoading={isLoading} />

      {/* 2. Controls & Filter Section */}
      <section className="dashboard-content-panel">
        <div className="panel-header-row">
          <div>
            <h3 className="panel-title">Scheduled Business Events</h3>
            <p className="panel-subtitle">
              Configured temporal events driving microservice cache prewarming
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-open-create"
            onClick={handleOpenCreate}
            aria-label="Create new scheduled event"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Create Event</span>
          </button>
        </div>

        {/* Success Toast Notification */}
        {successToast && (
          <div className="success-toast-banner" role="status" aria-live="polite">
            <div className="toast-content">
              <span className="toast-icon" aria-hidden="true">
                ✓
              </span>
              <span className="toast-message">{successToast.message}</span>
            </div>
            <button
              type="button"
              className="btn-toast-dismiss"
              onClick={() => setSuccessToast(null)}
              aria-label="Dismiss notification"
            >
              ×
            </button>
          </div>
        )}

        <EventFilters
          filters={filters}
          onChange={handleFilterChange}
          onClear={handleClearFilters}
          isFiltered={isFiltered}
        />

        {/* Client-side search notice when search term is active */}
        {filters.searchTerm && (
          <div className="search-filter-banner">
            <span>
              Filtering loaded page for: &ldquo;<strong>{filters.searchTerm}</strong>&rdquo;
              ({displayedEvents.length} matching of {events.length} loaded records).
            </span>
          </div>
        )}

        {/* 3. Main State Render */}
        {isLoading && <LoadingSpinner message="Fetching events from MongoDB Atlas…" />}

        {errorMessage && !isLoading && (
          <ErrorState
            title="Failed to load events"
            message={errorMessage}
            onRetry={() => loadDashboardData(currentPage)}
          />
        )}

        {!isLoading && !errorMessage && (
          <EventsTable
            events={displayedEvents}
            pagination={pagination}
            onPageChange={handlePageChange}
            isFiltered={isFiltered}
            onClearFilters={handleClearFilters}
            onEdit={handleOpenEdit}
            onViewDetails={handleOpenDetails}
          />
        )}
      </section>

      {/* 4. Create / Edit Event Modal */}
      <EventFormModal
        isOpen={isModalOpen}
        mode={modalMode}
        initialEvent={selectedEvent}
        onClose={handleModalClose}
        onSuccess={handleMutationSuccess}
      />

      {/* 5. Event Details Modal (Part 3.4) */}
      <EventDetailsModal
        isOpen={isDetailsModalOpen}
        eventId={selectedDetailsEventId}
        onClose={handleCloseDetails}
        onEdit={handleEditFromDetails}
        onEventCancelled={handleEventCancelled}
        onEventDeleted={handleEventDeleted}
      />
    </div>
  );
};
