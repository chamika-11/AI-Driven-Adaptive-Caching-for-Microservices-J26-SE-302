// ─────────────────────────────────────────────────────────────────────────────
// Scheduled Events Table Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Accessible table rendering verified event contracts with pagination controls.
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";
import type { ScheduledEvent, PaginationMeta } from "@component4/shared";
import { formatDateTime, formatDurationMinutes } from "../../utils/date.js";
import {
  StatusBadge,
  PriorityBadge,
  ExpectedLoadBadge,
} from "../common/Badge.js";
import { EmptyState } from "../common/EmptyState.js";

interface EventsTableProps {
  events: ScheduledEvent[];
  pagination: PaginationMeta;
  onPageChange: (newPage: number) => void;
  isFiltered: boolean;
  onClearFilters: () => void;
  onEdit?: (event: ScheduledEvent) => void;
  onViewDetails?: (event: ScheduledEvent) => void;
}

export const EventsTable: React.FC<EventsTableProps> = ({
  events,
  pagination,
  onPageChange,
  isFiltered,
  onClearFilters,
  onEdit,
  onViewDetails,
}) => {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No scheduled events found"
        message={
          isFiltered
            ? "No events match the selected filters. Try broadening your search or resetting filters."
            : "No events are currently scheduled in the database."
        }
        isFiltered={isFiltered}
        onClearFilters={onClearFilters}
      />
    );
  }

  const startRecord = (pagination.page - 1) * pagination.limit + 1;
  const endRecord = Math.min(
    pagination.page * pagination.limit,
    pagination.total
  );

  return (
    <div className="table-section">
      <div className="table-responsive-wrapper">
        <table className="events-table" aria-label="Scheduled Business Events">
          <thead>
            <tr>
              <th scope="col" style={{ width: "26%" }}>
                Event Details
              </th>
              <th scope="col" style={{ width: "13%" }}>
                Category
              </th>
              <th scope="col" style={{ width: "16%" }}>
                Start Time
              </th>
              <th scope="col" style={{ width: "16%" }}>
                End Time
              </th>
              <th scope="col" style={{ width: "9%" }}>
                Priority
              </th>
              <th scope="col" style={{ width: "9%" }}>
                Load
              </th>
              <th scope="col" style={{ width: "8%" }}>
                Prewarm
              </th>
              <th scope="col" style={{ width: "9%" }}>
                Status
              </th>
              <th scope="col" style={{ width: "8%" }}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.eventId} className="event-row">
                {/* Event Name & Description */}
                <td className="cell-event-details">
                  {onViewDetails ? (
                    <button
                      type="button"
                      className="event-name-link"
                      onClick={() => onViewDetails(event)}
                      title={`View details for ${event.eventName}`}
                      aria-label={event.eventName}
                    >
                      {event.eventName}
                    </button>
                  ) : (
                    <div className="event-name-title" title={event.eventName}>
                      {event.eventName}
                    </div>
                  )}
                  {event.description && (
                    <div className="event-description-text" title={event.description}>
                      {event.description}
                    </div>
                  )}
                  <div className="event-id-subtext">ID: {event.eventId}</div>
                </td>

                {/* Event Type */}
                <td className="cell-type">
                  <span className="type-tag">{event.eventType.replace(/_/g, " ")}</span>
                </td>

                {/* Start Time */}
                <td className="cell-datetime">
                  <span className="datetime-text">
                    {formatDateTime(event.startTime)}
                  </span>
                </td>

                {/* End Time */}
                <td className="cell-datetime">
                  <span className="datetime-text">
                    {formatDateTime(event.endTime)}
                  </span>
                </td>

                {/* Priority */}
                <td className="cell-priority">
                  <PriorityBadge priority={event.priority} />
                </td>

                {/* Expected Load */}
                <td className="cell-load">
                  <ExpectedLoadBadge load={event.expectedLoad} />
                </td>

                {/* Prewarm Window */}
                <td className="cell-prewarm">
                  <span className="prewarm-badge">
                    {formatDurationMinutes(event.prewarmWindowMinutes)}
                  </span>
                </td>

                {/* Status */}
                <td className="cell-status">
                  <StatusBadge status={event.status} />
                </td>

                {/* Actions */}
                <td className="cell-actions">
                  <div className="table-actions-group">
                    {onViewDetails && (
                      <button
                        type="button"
                        className="btn btn-sm btn-view-event"
                        onClick={() => onViewDetails(event)}
                        aria-label={`View details for ${event.eventName}`}
                      >
                        <svg
                          width="13"
                          height="13"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                        View
                      </button>
                    )}
                    {onEdit && (
                      <button
                        type="button"
                        className="btn btn-sm btn-edit-event"
                        onClick={() => onEdit(event)}
                        aria-label={`Edit ${event.eventName}`}
                      >
                        <svg
                          width="13"
                          height="13"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                        Edit
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <footer className="pagination-bar" aria-label="Table Pagination">
        <div className="pagination-info">
          Showing <span className="font-semibold">{startRecord}</span> to{" "}
          <span className="font-semibold">{endRecord}</span> of{" "}
          <span className="font-semibold">{pagination.total}</span> events
        </div>

        <div className="pagination-controls">
          <button
            type="button"
            className="btn btn-pagination"
            onClick={() => onPageChange(pagination.page - 1)}
            disabled={pagination.page <= 1}
            aria-label="Previous page"
          >
            Previous
          </button>

          <span className="page-indicator">
            Page {pagination.page} of {Math.max(1, pagination.totalPages)}
          </span>

          <button
            type="button"
            className="btn btn-pagination"
            onClick={() => onPageChange(pagination.page + 1)}
            disabled={pagination.page >= pagination.totalPages}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      </footer>
    </div>
  );
};
