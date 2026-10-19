// ─────────────────────────────────────────────────────────────────────────────
// Top Header Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";
import { getHeaderCurrentDate } from "../../utils/date.js";

interface HeaderProps {
  title: string;
  subtitle: string;
  isRefreshing: boolean;
  onRefresh: () => void;
  systemStatus?: {
    connected: boolean;
    database?: string;
  } | null;
  onToggleMobileMenu: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  subtitle,
  isRefreshing,
  onRefresh,
  systemStatus,
  onToggleMobileMenu,
}) => {
  const currentDate = getHeaderCurrentDate();

  return (
    <header className="app-header">
      <div className="header-left">
        <button
          type="button"
          className="btn-mobile-menu"
          onClick={onToggleMobileMenu}
          aria-label="Toggle navigation menu"
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>

        <div className="header-title-wrapper">
          <h2 className="header-title">{title}</h2>
          <p className="header-subtitle">{subtitle}</p>
        </div>
      </div>

      <div className="header-actions">
        {/* System Readiness Pill */}
        {systemStatus !== undefined && (
          <div
            className={`system-status-pill ${
              systemStatus?.connected ? "status-online" : "status-offline"
            }`}
            role="status"
            aria-label={`API Status: ${
              systemStatus?.connected ? "Online" : "Disconnected"
            }`}
          >
            <span className="status-dot" aria-hidden="true" />
            <span className="status-label">
              {systemStatus?.connected
                ? `API Online (${systemStatus.database ?? "MongoDB Ready"})`
                : "API Disconnected"}
            </span>
          </div>
        )}

        {/* Current Date Badge */}
        <div className="header-date" aria-label={`Current date: ${currentDate}`}>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
          <span>{currentDate}</span>
        </div>

        {/* Refresh Action */}
        <button
          type="button"
          className={`btn btn-refresh ${isRefreshing ? "btn-refreshing" : ""}`}
          onClick={onRefresh}
          disabled={isRefreshing}
          aria-label="Refresh dashboard events"
          title="Refresh events"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={isRefreshing ? "spin-icon" : ""}
            aria-hidden="true"
          >
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          <span className="refresh-text">{isRefreshing ? "Refreshing…" : "Refresh"}</span>
        </button>
      </div>
    </header>
  );
};
