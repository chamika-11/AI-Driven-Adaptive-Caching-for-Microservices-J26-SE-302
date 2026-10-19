// ─────────────────────────────────────────────────────────────────────────────
// Sidebar Navigation Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Charcoal/Navy sidebar with accessible navigation and mobile drawer behavior.
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";

export type NavTab = "dashboard" | "events" | "api-docs" | "settings";

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  isOpenOnMobile: boolean;
  onCloseMobile: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  isOpenOnMobile,
  onCloseMobile,
}) => {
  const handleNavClick = (tab: NavTab) => {
    onSelectTab(tab);
    onCloseMobile();
  };

  return (
    <>
      {/* Mobile overlay backdrop */}
      {isOpenOnMobile && (
        <div
          className="sidebar-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={`sidebar ${isOpenOnMobile ? "sidebar-mobile-open" : ""}`}
        aria-label="Application Navigation"
      >
        <div className="sidebar-brand">
          <div className="brand-icon" aria-hidden="true">
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
          </div>
          <div className="brand-text">
            <h1 className="brand-title">Event Intelligence</h1>
            <span className="brand-subtitle">Component 4 • Adaptive Cache</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">MAIN NAVIGATION</div>

          <button
            type="button"
            className={`nav-item ${activeTab === "dashboard" ? "nav-item-active" : ""}`}
            onClick={() => handleNavClick("dashboard")}
            aria-current={activeTab === "dashboard" ? "page" : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </svg>
            </span>
            <span className="nav-label">Dashboard</span>
          </button>

          <button
            type="button"
            className={`nav-item ${activeTab === "events" ? "nav-item-active" : ""}`}
            onClick={() => handleNavClick("events")}
            aria-current={activeTab === "events" ? "page" : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
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
            </span>
            <span className="nav-label">Events</span>
          </button>

          <div className="nav-section-label" style={{ marginTop: "1.5rem" }}>
            FUTURE MODULES
          </div>

          <button
            type="button"
            className={`nav-item ${activeTab === "api-docs" ? "nav-item-active" : ""}`}
            onClick={() => handleNavClick("api-docs")}
            aria-current={activeTab === "api-docs" ? "page" : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </span>
            <span className="nav-label">API Documentation</span>
            <span className="nav-badge-pill">Soon</span>
          </button>

          <button
            type="button"
            className={`nav-item ${activeTab === "settings" ? "nav-item-active" : ""}`}
            onClick={() => handleNavClick("settings")}
            aria-current={activeTab === "settings" ? "page" : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </span>
            <span className="nav-label">Settings</span>
            <span className="nav-badge-pill">Soon</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <span className="footer-label">Component Version</span>
          <span className="footer-value">v0.1.0 (Part 3.2)</span>
        </div>
      </aside>
    </>
  );
};
