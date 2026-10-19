// ─────────────────────────────────────────────────────────────────────────────
// Event Form Modal Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Accessible modal dialog for creating and editing scheduled business events.
// Reuses shared Zod contracts and validates timezone-aware date/time inputs.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useRef } from "react";
import {
  EVENT_TYPES,
  EXPECTED_LOADS,
  EVENT_PRIORITIES,
  CreateScheduledEventInputSchema,
  UpdateScheduledEventInputSchema,
  type EventType,
  type ExpectedLoad,
  type EventPriority,
  type ScheduledEvent,
  type CreateScheduledEventInput,
  type UpdateScheduledEventInput,
} from "@component4/shared";
import {
  createEvent,
  updateEvent,
} from "../../services/events.service.js";
import { ApiError } from "../../services/api.client.js";
import {
  isoToDatetimeLocal,
  datetimeLocalToIso,
  getLocalTimezoneLabel,
} from "../../utils/date.js";

export interface EventFormModalProps {
  isOpen: boolean;
  mode: "create" | "edit";
  initialEvent?: ScheduledEvent | null;
  onClose: () => void;
  onSuccess: (event: ScheduledEvent, action: "created" | "updated") => void;
}

export const EventFormModal: React.FC<EventFormModalProps> = ({
  isOpen,
  mode,
  initialEvent,
  onClose,
  onSuccess,
}) => {
  const [eventName, setEventName] = useState<string>("");
  const [eventType, setEventType] = useState<EventType | "">("");
  const [description, setDescription] = useState<string>("");
  const [startTime, setStartTime] = useState<string>("");
  const [endTime, setEndTime] = useState<string>("");
  const [expectedLoad, setExpectedLoad] = useState<ExpectedLoad | "">("");
  const [priority, setPriority] = useState<EventPriority | "">("");
  const [prewarmWindowMinutes, setPrewarmWindowMinutes] = useState<string>("30");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [apiErrorMessage, setApiErrorMessage] = useState<string | null>(null);
  const [apiIssues, setApiIssues] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const firstInputRef = useRef<HTMLInputElement | null>(null);
  const modalRef = useRef<HTMLDivElement | null>(null);

  // Initialize or reset form state when modal opens or initialEvent changes
  useEffect(() => {
    if (!isOpen) return;

    setFieldErrors({});
    setApiErrorMessage(null);
    setApiIssues([]);
    setIsSubmitting(false);

    if (mode === "edit" && initialEvent) {
      setEventName(initialEvent.eventName);
      setEventType(initialEvent.eventType);
      setDescription(initialEvent.description ?? "");
      setStartTime(isoToDatetimeLocal(initialEvent.startTime));
      setEndTime(isoToDatetimeLocal(initialEvent.endTime));
      setExpectedLoad(initialEvent.expectedLoad ?? "");
      setPriority(initialEvent.priority ?? "");
      setPrewarmWindowMinutes(String(initialEvent.prewarmWindowMinutes));
    } else {
      setEventName("");
      setEventType("");
      setDescription("");
      setStartTime("");
      setEndTime("");
      setExpectedLoad("");
      setPriority("");
      setPrewarmWindowMinutes("30");
    }

    // Auto-focus first input on next tick
    const timer = setTimeout(() => {
      firstInputRef.current?.focus();
    }, 50);

    return () => clearTimeout(timer);
  }, [isOpen, mode, initialEvent]);

  // Handle Escape key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) return null;

  const timezoneLabel = getLocalTimezoneLabel();

  /**
   * Form submission handler for Create and Edit.
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    setFieldErrors({});
    setApiErrorMessage(null);
    setApiIssues([]);

    const errors: Record<string, string> = {};

    // 1. Basic validation
    const trimmedName = eventName.trim();
    if (!trimmedName) {
      errors.eventName = "Event name is required";
    }

    if (!eventType) {
      errors.eventType = "Event type is required";
    }

    if (!startTime) {
      errors.startTime = "Start time is required";
    }

    if (!endTime) {
      errors.endTime = "End time is required";
    }

    const prewarmNum = Number(prewarmWindowMinutes);
    if (
      prewarmWindowMinutes.trim() === "" ||
      isNaN(prewarmNum) ||
      !Number.isInteger(prewarmNum)
    ) {
      errors.prewarmWindowMinutes = "Prewarm window must be an integer";
    } else if (prewarmNum < 0) {
      errors.prewarmWindowMinutes = "Prewarm window must be at least 0";
    } else if (prewarmNum > 10080) {
      errors.prewarmWindowMinutes = "Prewarm window must not exceed 10080 minutes";
    }

    // Convert local dates to ISO strings with explicit timezone offsets
    const startIso = startTime ? datetimeLocalToIso(startTime) : "";
    const endIso = endTime ? datetimeLocalToIso(endTime) : "";

    if (startIso && endIso) {
      const startTimeMs = new Date(startIso).getTime();
      const endTimeMs = new Date(endIso).getTime();
      if (endTimeMs <= startTimeMs) {
        errors.endTime = "End time must be later than start time";
      }
    }

    // Stop if basic checks fail
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    try {
      setIsSubmitting(true);

      if (mode === "create") {
        const createPayload: CreateScheduledEventInput = {
          eventName: trimmedName,
          eventType: eventType as EventType,
          description: description.trim() || undefined,
          startTime: startIso,
          endTime: endIso,
          expectedLoad: expectedLoad ? (expectedLoad as ExpectedLoad) : undefined,
          priority: priority ? (priority as EventPriority) : undefined,
          prewarmWindowMinutes: prewarmNum,
        };

        // Validate using shared Zod schema
        const zodCheck = CreateScheduledEventInputSchema.safeParse(createPayload);
        if (!zodCheck.success) {
          const zodErrors: Record<string, string> = {};
          for (const issue of zodCheck.error.issues) {
            const field = String(issue.path[0]);
            if (field && !zodErrors[field]) {
              zodErrors[field] = issue.message;
            }
          }
          setFieldErrors(zodErrors);
          setIsSubmitting(false);
          return;
        }

        const created = await createEvent(createPayload);
        onSuccess(created, "created");
        onClose();
      } else {
        // Edit mode
        if (!initialEvent) {
          setApiErrorMessage("No event selected to update");
          setIsSubmitting(false);
          return;
        }

        // Build partial update payload containing only modified editable fields
        const updatePayload: UpdateScheduledEventInput = {};

        if (trimmedName !== initialEvent.eventName) {
          updatePayload.eventName = trimmedName;
        }
        if (eventType !== initialEvent.eventType) {
          updatePayload.eventType = eventType as EventType;
        }
        const cleanDesc = description.trim() || undefined;
        if (cleanDesc !== (initialEvent.description || undefined)) {
          updatePayload.description = cleanDesc;
        }
        if (startIso !== initialEvent.startTime) {
          updatePayload.startTime = startIso;
        }
        if (endIso !== initialEvent.endTime) {
          updatePayload.endTime = endIso;
        }
        const cleanLoad = expectedLoad ? (expectedLoad as ExpectedLoad) : undefined;
        if (cleanLoad !== (initialEvent.expectedLoad || undefined)) {
          updatePayload.expectedLoad = cleanLoad;
        }
        const cleanPriority = priority ? (priority as EventPriority) : undefined;
        if (cleanPriority !== (initialEvent.priority || undefined)) {
          updatePayload.priority = cleanPriority;
        }
        if (prewarmNum !== initialEvent.prewarmWindowMinutes) {
          updatePayload.prewarmWindowMinutes = prewarmNum;
        }

        // If no fields changed, simply close without making unnecessary HTTP call
        if (Object.keys(updatePayload).length === 0) {
          onClose();
          return;
        }

        // Validate cross-field date window against the resulting state
        const resultingStart = updatePayload.startTime ?? initialEvent.startTime;
        const resultingEnd = updatePayload.endTime ?? initialEvent.endTime;
        if (new Date(resultingEnd).getTime() <= new Date(resultingStart).getTime()) {
          setFieldErrors({ endTime: "End time must be later than start time" });
          setIsSubmitting(false);
          return;
        }

        // Validate using shared Zod schema
        const zodCheck = UpdateScheduledEventInputSchema.safeParse(updatePayload);
        if (!zodCheck.success) {
          const zodErrors: Record<string, string> = {};
          for (const issue of zodCheck.error.issues) {
            const field = String(issue.path[0]);
            if (field && !zodErrors[field]) {
              zodErrors[field] = issue.message;
            }
          }
          setFieldErrors(zodErrors);
          setIsSubmitting(false);
          return;
        }

        const updated = await updateEvent(initialEvent.eventId, updatePayload);
        onSuccess(updated, "updated");
        onClose();
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setApiErrorMessage(err.message);
        if (err.issues && err.issues.length > 0) {
          setApiIssues(err.issues);
          // Map backend field-level issues (format "field: message")
          const backendFieldErrors: Record<string, string> = {};
          for (const issue of err.issues) {
            const colonIdx = issue.indexOf(":");
            if (colonIdx > 0) {
              const fieldName = issue.substring(0, colonIdx).trim();
              const message = issue.substring(colonIdx + 1).trim();
              if (fieldName && message && !backendFieldErrors[fieldName]) {
                backendFieldErrors[fieldName] = message;
              }
            }
          }
          if (Object.keys(backendFieldErrors).length > 0) {
            setFieldErrors((prev) => ({ ...prev, ...backendFieldErrors }));
          }
        }
      } else {
        const msg =
          err instanceof Error
            ? err.message
            : "An unexpected network error occurred. Please try again.";
        setApiErrorMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
      role="presentation"
    >
      <div
        className="modal-container"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="modal-header">
          <div>
            <h2 id="modal-title" className="modal-title">
              {mode === "create" ? "Create Scheduled Event" : "Edit Scheduled Event"}
            </h2>
            <p className="modal-subtitle">
              {mode === "create"
                ? "Configure a new business event to drive microservice cache prewarming"
                : `Update configuration for event identifier: ${initialEvent?.eventId ?? ""}`}
            </p>
          </div>
          <button
            type="button"
            className="btn-modal-close"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
          >
            ×
          </button>
        </div>

        {/* Global Error Banner */}
        {apiErrorMessage && (
          <div className="form-error-banner" role="alert">
            <div className="error-banner-header">
              <span className="error-banner-icon" aria-hidden="true">
                ⚠️
              </span>
              <strong>{apiErrorMessage}</strong>
            </div>
            {apiIssues.length > 0 && (
              <ul className="error-banner-list">
                {apiIssues.map((issue, idx) => (
                  <li key={idx}>{issue}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="event-modal-form">
          {/* Row 1: Event Name */}
          <div className="form-group">
            <label htmlFor="eventName" className="form-label">
              Event Name <span className="required-star">*</span>
              <span className="sr-only">(required)</span>
            </label>
            <input
              ref={firstInputRef}
              id="eventName"
              type="text"
              className={`form-input ${fieldErrors.eventName ? "input-error" : ""}`}
              placeholder="e.g. Semester 1 Examination Results Release"
              value={eventName}
              onChange={(e) => {
                setEventName(e.target.value);
                if (fieldErrors.eventName) {
                  setFieldErrors((prev) => ({ ...prev, eventName: "" }));
                }
              }}
              disabled={isSubmitting}
              maxLength={200}
              aria-required="true"
              aria-invalid={Boolean(fieldErrors.eventName)}
              aria-describedby={fieldErrors.eventName ? "eventName-error" : undefined}
            />
            {fieldErrors.eventName && (
              <span id="eventName-error" className="field-error-text" role="alert">
                {fieldErrors.eventName}
              </span>
            )}
          </div>

          {/* Row 2: Event Type & Prewarm Window */}
          <div className="form-row two-col">
            <div className="form-group">
              <label htmlFor="eventType" className="form-label">
                Event Type <span className="required-star">*</span>
                <span className="sr-only">(required)</span>
              </label>
              <select
                id="eventType"
                className={`form-select ${fieldErrors.eventType ? "input-error" : ""}`}
                value={eventType}
                onChange={(e) => {
                  setEventType(e.target.value as EventType | "");
                  if (fieldErrors.eventType) {
                    setFieldErrors((prev) => ({ ...prev, eventType: "" }));
                  }
                }}
                disabled={isSubmitting}
                aria-required="true"
                aria-invalid={Boolean(fieldErrors.eventType)}
                aria-describedby={fieldErrors.eventType ? "eventType-error" : undefined}
              >
                <option value="">Select Event Type…</option>
                {EVENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
              {fieldErrors.eventType && (
                <span id="eventType-error" className="field-error-text" role="alert">
                  {fieldErrors.eventType}
                </span>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="prewarmWindowMinutes" className="form-label">
                Prewarm Window (Minutes) <span className="required-star">*</span>
                <span className="sr-only">(required)</span>
              </label>
              <input
                id="prewarmWindowMinutes"
                type="number"
                min={0}
                max={10080}
                step={1}
                className={`form-input ${
                  fieldErrors.prewarmWindowMinutes ? "input-error" : ""
                }`}
                placeholder="e.g. 60"
                value={prewarmWindowMinutes}
                onChange={(e) => {
                  setPrewarmWindowMinutes(e.target.value);
                  if (fieldErrors.prewarmWindowMinutes) {
                    setFieldErrors((prev) => ({
                      ...prev,
                      prewarmWindowMinutes: "",
                    }));
                  }
                }}
                disabled={isSubmitting}
                aria-required="true"
                aria-invalid={Boolean(fieldErrors.prewarmWindowMinutes)}
                aria-describedby={
                  fieldErrors.prewarmWindowMinutes
                    ? "prewarmWindowMinutes-error"
                    : "prewarm-help"
                }
              />
              <span id="prewarm-help" className="field-help-text">
                Lead time before start to trigger cache prewarming (0 to 10080 min).
              </span>
              {fieldErrors.prewarmWindowMinutes && (
                <span
                  id="prewarmWindowMinutes-error"
                  className="field-error-text"
                  role="alert"
                >
                  {fieldErrors.prewarmWindowMinutes}
                </span>
              )}
            </div>
          </div>

          {/* Row 3: Start Time & End Time */}
          <div className="form-row two-col">
            <div className="form-group">
              <label htmlFor="startTime" className="form-label">
                Start Date & Time <span className="required-star">*</span>
                <span className="sr-only">(required)</span>
              </label>
              <input
                id="startTime"
                type="datetime-local"
                className={`form-input ${fieldErrors.startTime ? "input-error" : ""}`}
                value={startTime}
                onChange={(e) => {
                  setStartTime(e.target.value);
                  if (fieldErrors.startTime) {
                    setFieldErrors((prev) => ({ ...prev, startTime: "" }));
                  }
                }}
                disabled={isSubmitting}
                aria-required="true"
                aria-invalid={Boolean(fieldErrors.startTime)}
                aria-describedby={fieldErrors.startTime ? "startTime-error" : undefined}
              />
              {fieldErrors.startTime && (
                <span id="startTime-error" className="field-error-text" role="alert">
                  {fieldErrors.startTime}
                </span>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="endTime" className="form-label">
                End Date & Time <span className="required-star">*</span>
                <span className="sr-only">(required)</span>
              </label>
              <input
                id="endTime"
                type="datetime-local"
                className={`form-input ${fieldErrors.endTime ? "input-error" : ""}`}
                value={endTime}
                onChange={(e) => {
                  setEndTime(e.target.value);
                  if (fieldErrors.endTime) {
                    setFieldErrors((prev) => ({ ...prev, endTime: "" }));
                  }
                }}
                disabled={isSubmitting}
                aria-required="true"
                aria-invalid={Boolean(fieldErrors.endTime)}
                aria-describedby={fieldErrors.endTime ? "endTime-error" : undefined}
              />
              {fieldErrors.endTime && (
                <span id="endTime-error" className="field-error-text" role="alert">
                  {fieldErrors.endTime}
                </span>
              )}
            </div>
          </div>

          {/* Timezone Information Callout */}
          <div className="timezone-callout" role="note">
            <span className="timezone-icon" aria-hidden="true">
              🌐
            </span>
            <span>
              Dates are interpreted in your local timezone: <strong>{timezoneLabel}</strong>.
              Values are submitted as ISO 8601 with explicit timezone offsets.
            </span>
          </div>

          {/* Row 4: Expected Load & Priority */}
          <div className="form-row two-col">
            <div className="form-group">
              <label htmlFor="expectedLoad" className="form-label">
                Expected Traffic Load <span className="optional-tag">(Optional)</span>
              </label>
              <select
                id="expectedLoad"
                className="form-select"
                value={expectedLoad}
                onChange={(e) =>
                  setExpectedLoad(e.target.value as ExpectedLoad | "")
                }
                disabled={isSubmitting}
              >
                <option value="">Select Expected Load…</option>
                {EXPECTED_LOADS.map((load) => (
                  <option key={load} value={load}>
                    {load}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="priority" className="form-label">
                Scheduling Priority <span className="optional-tag">(Optional)</span>
              </label>
              <select
                id="priority"
                className="form-select"
                value={priority}
                onChange={(e) =>
                  setPriority(e.target.value as EventPriority | "")
                }
                disabled={isSubmitting}
              >
                <option value="">Select Priority…</option>
                {EVENT_PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Row 5: Description */}
          <div className="form-group">
            <label htmlFor="description" className="form-label">
              Description <span className="optional-tag">(Optional)</span>
            </label>
            <textarea
              id="description"
              rows={3}
              className={`form-textarea ${
                fieldErrors.description ? "input-error" : ""
              }`}
              placeholder="Provide background context on affected microservices and peak query patterns…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              maxLength={2000}
            />
            {fieldErrors.description && (
              <span id="description-error" className="field-error-text" role="alert">
                {fieldErrors.description}
              </span>
            )}
          </div>

          {/* Modal Actions */}
          <div className="modal-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary btn-submit-event"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className="spinner-sm" aria-hidden="true" />
                  <span>{mode === "create" ? "Creating…" : "Saving…"}</span>
                </>
              ) : (
                <span>{mode === "create" ? "Create Event" : "Save Changes"}</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
