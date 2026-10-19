// ─────────────────────────────────────────────────────────────────────────────
// Event Details Modal Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Accessible modal dialog inspecting full event metadata and executing lifecycle actions.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useCallback, useRef } from "react";
import type { ScheduledEvent } from "@component4/shared";
import {
  getEventById,
  cancelEvent,
  deleteEvent,
} from "../../services/events.service.js";
import { ApiError } from "../../services/api.client.js";
import {
  formatDateTime,
  formatDurationMinutes,
  getLocalTimezoneLabel,
} from "../../utils/date.js";
import {
  StatusBadge,
  PriorityBadge,
  ExpectedLoadBadge,
} from "../common/Badge.js";
import { LoadingSpinner } from "../common/LoadingSpinner.js";
import { ErrorState } from "../common/ErrorState.js";
import { ConfirmationModal } from "../common/ConfirmationModal.js";

export interface EventDetailsModalProps {
  isOpen: boolean;
  eventId: string | null;
  onClose: () => void;
  onEdit: (event: ScheduledEvent) => void;
  onEventCancelled: (event: ScheduledEvent) => void;
  onEventDeleted: (eventId: string, eventName: string) => void;
}

export const EventDetailsModal: React.FC<EventDetailsModalProps> = ({
  isOpen,
  eventId,
  onClose,
  onEdit,
  onEventCancelled,
  onEventDeleted,
}) => {
  const [event, setEvent] = useState<ScheduledEvent | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isNotFound, setIsNotFound] = useState<boolean>(false);

  // Cancellation confirmation state
  const [isCancelConfirmOpen, setIsCancelConfirmOpen] = useState<boolean>(false);
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [cancelErrorMessage, setCancelErrorMessage] = useState<string | null>(null);

  // Deletion confirmation state
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState<string | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  /**
   * Fetches fresh event details from GET /api/events/:eventId
   */
  const fetchDetails = useCallback(
    async (signal?: AbortSignal) => {
      if (!eventId) return;

      setIsLoading(true);
      setErrorMessage(null);
      setIsNotFound(false);

      try {
        const data = await getEventById(eventId, signal);
        setEvent(data);
      } catch (err: unknown) {
        if (
          (err instanceof Error && err.name === "AbortError") ||
          (typeof DOMException !== "undefined" &&
            err instanceof DOMException &&
            err.name === "AbortError")
        ) {
          return;
        }

        if (err instanceof ApiError && err.statusCode === 404) {
          setIsNotFound(true);
          setErrorMessage(
            `The requested event with identifier '${eventId}' could not be found. It may have been deleted.`
          );
        } else {
          const msg =
            err instanceof Error
              ? err.message
              : "Failed to load event details from MongoDB Atlas.";
          setErrorMessage(msg);
        }
      } finally {
        setIsLoading(false);
      }
    },
    [eventId]
  );

  useEffect(() => {
    if (!isOpen || !eventId) {
      setEvent(null);
      setIsLoading(false);
      setErrorMessage(null);
      return;
    }

    const controller = new AbortController();
    fetchDetails(controller.signal);

    return () => {
      controller.abort();
    };
  }, [isOpen, eventId, fetchDetails]);

  // Keyboard accessibility: Escape key closes modal (if no confirmation is active)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === "Escape" &&
        !isCancelConfirmOpen &&
        !isDeleteConfirmOpen &&
        !isCancelling &&
        !isDeleting
      ) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    closeButtonRef.current?.focus();

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, isCancelConfirmOpen, isDeleteConfirmOpen, isCancelling, isDeleting, onClose]);

  if (!isOpen) return null;

  // Lifecycle check: Only SCHEDULED events may be cancelled
  const isCancellable = event?.status === "SCHEDULED";

  /**
   * Confirmed Cancellation execution
   */
  const handleConfirmCancel = async () => {
    if (!event) return;

    setIsCancelling(true);
    setCancelErrorMessage(null);

    try {
      const updated = await cancelEvent(event.eventId);
      setEvent(updated);
      setIsCancelConfirmOpen(false);
      onEventCancelled(updated);
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to cancel event. Please try again.";
      setCancelErrorMessage(msg);
    } finally {
      setIsCancelling(false);
    }
  };

  /**
   * Confirmed Deletion execution
   */
  const handleConfirmDelete = async () => {
    if (!event) return;

    setIsDeleting(true);
    setDeleteErrorMessage(null);

    try {
      await deleteEvent(event.eventId);
      setIsDeleteConfirmOpen(false);
      onEventDeleted(event.eventId, event.eventName);
      onClose();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to delete event. Please try again.";
      setDeleteErrorMessage(msg);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <div
        className="modal-backdrop"
        onClick={(e) => {
          if (
            e.target === e.currentTarget &&
            !isCancelling &&
            !isDeleting &&
            !isCancelConfirmOpen &&
            !isDeleteConfirmOpen
          ) {
            onClose();
          }
        }}
        role="presentation"
      >
        <div
          className="modal-container event-details-modal-container"
          ref={modalRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="details-title"
        >
          {/* Header */}
          <div className="modal-header">
            <div>
              <div className="details-header-meta">
                <span className="details-kicker">Event Details</span>
                {event && <StatusBadge status={event.status} />}
              </div>
              <h2 id="details-title" className="modal-title details-modal-title">
                {event ? event.eventName : "Scheduled Event Inspection"}
              </h2>
              {event && (
                <div className="details-id-display">
                  <span className="details-id-label">Application Event ID:</span>
                  <code className="details-id-code">{event.eventId}</code>
                </div>
              )}
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              className="btn-modal-close"
              onClick={onClose}
              disabled={isCancelling || isDeleting}
              aria-label="Close details dialog"
            >
              ×
            </button>
          </div>

          {/* Modal Content */}
          <div className="details-modal-content">
            {isLoading && (
              <div className="details-loading-wrapper">
                <LoadingSpinner message="Fetching event specification from MongoDB Atlas…" />
              </div>
            )}

            {errorMessage && !isLoading && (
              <div className="details-error-wrapper">
                <ErrorState
                  title={isNotFound ? "Event Not Found" : "Error Loading Event"}
                  message={errorMessage}
                  onRetry={isNotFound ? undefined : () => fetchDetails()}
                />
                {isNotFound && (
                  <div className="details-notfound-actions">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={onClose}
                    >
                      Return to Events Dashboard
                    </button>
                  </div>
                )}
              </div>
            )}

            {!isLoading && !errorMessage && event && (
              <div className="details-data-container">
                {/* Timezone Notice Banner */}
                <div className="details-timezone-banner" role="note">
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  <span>
                    Timestamp transparency: Times displayed in{" "}
                    <strong>{getLocalTimezoneLabel()}</strong>
                  </span>
                </div>

                {/* Grid 1: Core Scheduling & Timeline */}
                <section className="details-section" aria-labelledby="section-timeline">
                  <h3 id="section-timeline" className="details-section-heading">
                    Schedule & Timing
                  </h3>
                  <div className="details-grid-two-col">
                    <div className="details-field-card">
                      <span className="field-card-label">Start Time</span>
                      <span className="field-card-value">{formatDateTime(event.startTime)}</span>
                      <span className="field-card-subtext">Event onset window</span>
                    </div>

                    <div className="details-field-card">
                      <span className="field-card-label">End Time</span>
                      <span className="field-card-value">{formatDateTime(event.endTime)}</span>
                      <span className="field-card-subtext">Event termination window</span>
                    </div>

                    <div className="details-field-card">
                      <span className="field-card-label">Prewarm Window</span>
                      <span className="field-card-value">
                        {event.prewarmWindowMinutes} minutes{" "}
                        <span className="field-card-badge">
                          ({formatDurationMinutes(event.prewarmWindowMinutes)})
                        </span>
                      </span>
                      <span className="field-card-subtext">
                        Lead time before onset to populate cache replicas
                      </span>
                    </div>

                    <div className="details-field-card">
                      <span className="field-card-label">Current Lifecycle Status</span>
                      <div className="field-card-value-badge">
                        <StatusBadge status={event.status} />
                      </div>
                      <span className="field-card-subtext">
                        System-managed operational lifecycle phase
                      </span>
                    </div>
                  </div>
                </section>

                {/* Grid 2: Classification & Resource Profiles */}
                <section className="details-section" aria-labelledby="section-profile">
                  <h3 id="section-profile" className="details-section-heading">
                    Classification & Impact Profile
                  </h3>
                  <div className="details-grid-three-col">
                    <div className="details-field-card">
                      <span className="field-card-label">Category / Type</span>
                      <span className="field-card-value-highlight">
                        {event.eventType.replace(/_/g, " ")}
                      </span>
                    </div>

                    <div className="details-field-card">
                      <span className="field-card-label">Anticipated Traffic Load</span>
                      <div className="field-card-value-badge">
                        <ExpectedLoadBadge load={event.expectedLoad} />
                      </div>
                    </div>

                    <div className="details-field-card">
                      <span className="field-card-label">Scheduling Priority</span>
                      <div className="field-card-value-badge">
                        <PriorityBadge priority={event.priority} />
                      </div>
                    </div>
                  </div>
                </section>

                {/* Description */}
                <section className="details-section" aria-labelledby="section-description">
                  <h3 id="section-description" className="details-section-heading">
                    Event Description
                  </h3>
                  <div className="details-description-box">
                    {event.description ? (
                      <p className="description-content">{event.description}</p>
                    ) : (
                      <p className="description-empty">No detailed description was provided.</p>
                    )}
                  </div>
                </section>

                {/* System Audit Information */}
                <section className="details-section details-audit-section" aria-labelledby="section-audit">
                  <h3 id="section-audit" className="details-section-heading">
                    System Audit Metadata
                  </h3>
                  <div className="details-audit-grid">
                    <div>
                      <span className="audit-label">Record Created:</span>{" "}
                      <span className="audit-value">{formatDateTime(event.createdAt)}</span>
                    </div>
                    <div>
                      <span className="audit-label">Last Modified:</span>{" "}
                      <span className="audit-value">{formatDateTime(event.updatedAt)}</span>
                    </div>
                  </div>
                  <p className="audit-note">
                    System audit timestamps are immutable.
                  </p>
                </section>

                {/* Lifecycle Cancellation Banner (if cancelled) */}
                {event.status === "CANCELLED" && (
                  <div className="details-cancelled-banner" role="status">
                    <span className="cancelled-banner-icon" aria-hidden="true">
                      ⚠️
                    </span>
                    <div>
                      <strong>This event is CANCELLED.</strong>
                      <p>
                        It will not trigger automated cache prewarming or feature extraction pipelines.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="modal-footer details-modal-footer">
            <div className="details-footer-left">
              {event && (
                <>
                  {/* Delete Button */}
                  <button
                    type="button"
                    className="btn btn-details-delete"
                    onClick={() => {
                      setDeleteErrorMessage(null);
                      setIsDeleteConfirmOpen(true);
                    }}
                    disabled={isCancelling || isDeleting}
                    aria-label={`Delete event ${event.eventName}`}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                    <span>Delete Event</span>
                  </button>

                  {/* Cancel Button (Visible/Enabled based on lifecycle status) */}
                  <button
                    type="button"
                    className="btn btn-details-cancel-lifecycle"
                    onClick={() => {
                      setCancelErrorMessage(null);
                      setIsCancelConfirmOpen(true);
                    }}
                    disabled={!isCancellable || isCancelling || isDeleting}
                    title={
                      isCancellable
                        ? "Cancel this scheduled event"
                        : `Cancellation is only permitted for SCHEDULED events (current status: ${event.status})`
                    }
                    aria-label={`Cancel scheduled event ${event.eventName}`}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                    </svg>
                    <span>Cancel Event</span>
                  </button>
                </>
              )}
            </div>

            <div className="details-footer-right">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
                disabled={isCancelling || isDeleting}
              >
                Close
              </button>

              {event && (
                <button
                  type="button"
                  className="btn btn-primary btn-details-edit"
                  onClick={() => {
                    onEdit(event);
                  }}
                  disabled={isCancelling || isDeleting}
                  aria-label={`Edit ${event.eventName}`}
                >
                  <svg
                    width="14"
                    height="14"
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
                  <span>Edit Event</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Confirmation Dialog: Cancel Event */}
      {event && (
        <ConfirmationModal
          isOpen={isCancelConfirmOpen}
          title="Cancel Scheduled Event?"
          message={`Are you sure you want to cancel "${event.eventName}" (${event.eventId})?`}
          details="Cancelling changes the event's lifecycle status to CANCELLED. Any planned cache prewarming windows will not be triggered."
          confirmLabel="Yes, Cancel Event"
          cancelLabel="Keep Scheduled"
          variant="warning"
          isPending={isCancelling}
          errorMessage={cancelErrorMessage}
          onConfirm={handleConfirmCancel}
          onCancel={() => {
            if (!isCancelling) {
              setIsCancelConfirmOpen(false);
              setCancelErrorMessage(null);
            }
          }}
        />
      )}

      {/* Confirmation Dialog: Delete Event */}
      {event && (
        <ConfirmationModal
          isOpen={isDeleteConfirmOpen}
          title="Permanently Delete Event?"
          message={`Are you sure you want to delete "${event.eventName}" (${event.eventId})?`}
          details="This action is permanent and irreversible. The event record will be permanently deleted from MongoDB Atlas and removed from all future telemetry."
          confirmLabel="Yes, Delete Event"
          cancelLabel="Keep Event"
          variant="danger"
          isPending={isDeleting}
          errorMessage={deleteErrorMessage}
          onConfirm={handleConfirmDelete}
          onCancel={() => {
            if (!isDeleting) {
              setIsDeleteConfirmOpen(false);
              setDeleteErrorMessage(null);
            }
          }}
        />
      )}
    </>
  );
};
