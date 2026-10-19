// ─────────────────────────────────────────────────────────────────────────────
// Empty State Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";

interface EmptyStateProps {
  title?: string;
  message?: string;
  isFiltered?: boolean;
  onClearFilters?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = "No scheduled events found",
  message = "No events match your current filter criteria or none have been scheduled yet.",
  isFiltered = false,
  onClearFilters,
}) => {
  return (
    <div className="empty-state-card" role="status">
      <div className="empty-icon" aria-hidden="true">
        <svg
          width="36"
          height="36"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
        </svg>
      </div>
      <h3 className="empty-title">{title}</h3>
      <p className="empty-message">{message}</p>
      {isFiltered && onClearFilters && (
        <button
          type="button"
          className="btn btn-secondary btn-clear-filters"
          onClick={onClearFilters}
          aria-label="Clear all applied filters"
        >
          Clear Filters
        </button>
      )}
    </div>
  );
};
