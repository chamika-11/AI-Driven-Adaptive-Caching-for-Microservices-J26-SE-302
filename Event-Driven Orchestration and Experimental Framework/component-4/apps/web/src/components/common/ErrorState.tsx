// ─────────────────────────────────────────────────────────────────────────────
// Error State Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = "Failed to load events",
  message,
  onRetry,
}) => {
  return (
    <div className="error-card" role="alert" aria-live="assertive">
      <div className="error-icon" aria-hidden="true">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <div className="error-content">
        <h3 className="error-title">{title}</h3>
        <p className="error-message">{message}</p>
        {onRetry && (
          <button
            type="button"
            className="btn btn-secondary btn-retry"
            onClick={onRetry}
            aria-label="Retry loading events"
          >
            Retry Request
          </button>
        )}
      </div>
    </div>
  );
};
