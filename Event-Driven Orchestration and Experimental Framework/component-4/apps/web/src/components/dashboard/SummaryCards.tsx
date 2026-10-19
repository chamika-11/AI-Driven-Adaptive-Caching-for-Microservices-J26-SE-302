// ─────────────────────────────────────────────────────────────────────────────
// Summary Cards Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Displays verified server-calculated event statistics across lifecycle states.
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";
import type { EventSummaryCounts } from "../../services/events.service.js";

interface SummaryCardsProps {
  counts: EventSummaryCounts;
  isLoading: boolean;
}

export const SummaryCards: React.FC<SummaryCardsProps> = ({ counts, isLoading }) => {
  return (
    <section className="summary-cards-grid" aria-label="Event Summary Statistics">
      {/* 1. Total Events */}
      <div className="summary-card card-total">
        <div className="card-header-row">
          <span className="card-label">TOTAL EVENTS</span>
          <div className="card-icon icon-total" aria-hidden="true">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </div>
        </div>
        <div className="card-value-row">
          <span className="card-value">
            {isLoading ? "—" : counts.total.toLocaleString()}
          </span>
        </div>
        <span className="card-description">Registered across all categories</span>
      </div>

      {/* 2. Scheduled Events */}
      <div className="summary-card card-scheduled">
        <div className="card-header-row">
          <span className="card-label">SCHEDULED</span>
          <div className="card-icon icon-scheduled" aria-hidden="true">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
        </div>
        <div className="card-value-row">
          <span className="card-value">
            {isLoading ? "—" : counts.scheduled.toLocaleString()}
          </span>
        </div>
        <span className="card-description">Pending prewarm & execution</span>
      </div>

      {/* 3. Completed Events */}
      <div className="summary-card card-completed">
        <div className="card-header-row">
          <span className="card-label">COMPLETED</span>
          <div className="card-icon icon-completed" aria-hidden="true">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
        </div>
        <div className="card-value-row">
          <span className="card-value">
            {isLoading ? "—" : counts.completed.toLocaleString()}
          </span>
        </div>
        <span className="card-description">Successfully finished windows</span>
      </div>

      {/* 4. Cancelled Events */}
      <div className="summary-card card-cancelled">
        <div className="card-header-row">
          <span className="card-label">CANCELLED</span>
          <div className="card-icon icon-cancelled" aria-hidden="true">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
        </div>
        <div className="card-value-row">
          <span className="card-value">
            {isLoading ? "—" : counts.cancelled.toLocaleString()}
          </span>
        </div>
        <span className="card-description">Cancelled or superseded</span>
      </div>
    </section>
  );
};
