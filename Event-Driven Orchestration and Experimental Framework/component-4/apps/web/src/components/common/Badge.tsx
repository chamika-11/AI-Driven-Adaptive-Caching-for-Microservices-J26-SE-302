// ─────────────────────────────────────────────────────────────────────────────
// Status & Priority Badges — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Accessible badge component using curated HSL color schemes with clear text labels.
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";
import type { EventStatus, EventPriority, ExpectedLoad } from "@component4/shared";

interface StatusBadgeProps {
  status: EventStatus;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const getStatusClass = (s: EventStatus): string => {
    switch (s) {
      case "SCHEDULED":
        return "badge-status-scheduled";
      case "PROCESSING":
        return "badge-status-processing";
      case "COMPLETED":
        return "badge-status-completed";
      case "CANCELLED":
        return "badge-status-cancelled";
      default:
        return "badge-status-default";
    }
  };

  return (
    <span
      className={`badge ${getStatusClass(status)}`}
      role="status"
      aria-label={`Event status: ${status}`}
    >
      <span className="badge-dot" aria-hidden="true" />
      {status}
    </span>
  );
};

interface PriorityBadgeProps {
  priority?: EventPriority;
}

export const PriorityBadge: React.FC<PriorityBadgeProps> = ({ priority }) => {
  if (!priority) return <span className="text-muted">—</span>;

  const getPriorityClass = (p: EventPriority): string => {
    switch (p) {
      case "CRITICAL":
        return "badge-priority-critical";
      case "HIGH":
        return "badge-priority-high";
      case "MEDIUM":
        return "badge-priority-medium";
      case "LOW":
        return "badge-priority-low";
      default:
        return "badge-priority-default";
    }
  };

  return (
    <span
      className={`badge ${getPriorityClass(priority)}`}
      aria-label={`Priority: ${priority}`}
    >
      {priority}
    </span>
  );
};

interface ExpectedLoadBadgeProps {
  load?: ExpectedLoad;
}

export const ExpectedLoadBadge: React.FC<ExpectedLoadBadgeProps> = ({ load }) => {
  if (!load) return <span className="text-muted">—</span>;

  return (
    <span
      className="badge badge-load"
      aria-label={`Expected Load: ${load}`}
    >
      {load}
    </span>
  );
};
