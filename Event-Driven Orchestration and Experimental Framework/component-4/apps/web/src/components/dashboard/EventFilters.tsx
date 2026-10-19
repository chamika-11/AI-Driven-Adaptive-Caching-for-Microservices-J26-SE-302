// ─────────────────────────────────────────────────────────────────────────────
// Event Filter & Search Controls — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";
import {
  EVENT_TYPES,
  EVENT_STATUSES,
  EVENT_PRIORITIES,
  type EventType,
  type EventStatus,
  type EventPriority,
} from "@component4/shared";

export interface FilterState {
  searchTerm: string;
  status: EventStatus | "";
  eventType: EventType | "";
  priority: EventPriority | "";
}

interface EventFiltersProps {
  filters: FilterState;
  onChange: (updated: Partial<FilterState>) => void;
  onClear: () => void;
  isFiltered: boolean;
}

export const EventFilters: React.FC<EventFiltersProps> = ({
  filters,
  onChange,
  onClear,
  isFiltered,
}) => {
  return (
    <div className="filters-bar" role="search" aria-label="Event Search and Filters">
      {/* Search Input */}
      <div className="filter-group search-group">
        <label htmlFor="search-input" className="filter-label">
          Search Events
        </label>
        <div className="search-input-wrapper">
          <svg
            className="search-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            id="search-input"
            type="text"
            className="input-text"
            placeholder="Search by event name…"
            value={filters.searchTerm}
            onChange={(e) => onChange({ searchTerm: e.target.value })}
          />
          {filters.searchTerm && (
            <button
              type="button"
              className="btn-clear-search"
              onClick={() => onChange({ searchTerm: "" })}
              aria-label="Clear search text"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Status Filter */}
      <div className="filter-group">
        <label htmlFor="status-filter" className="filter-label">
          Status
        </label>
        <select
          id="status-filter"
          className="select-dropdown"
          value={filters.status}
          onChange={(e) => onChange({ status: e.target.value as EventStatus | "" })}
        >
          <option value="">All Statuses</option>
          {EVENT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </div>

      {/* Event Type Filter */}
      <div className="filter-group">
        <label htmlFor="type-filter" className="filter-label">
          Event Type
        </label>
        <select
          id="type-filter"
          className="select-dropdown"
          value={filters.eventType}
          onChange={(e) => onChange({ eventType: e.target.value as EventType | "" })}
        >
          <option value="">All Types</option>
          {EVENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      {/* Priority Filter */}
      <div className="filter-group">
        <label htmlFor="priority-filter" className="filter-label">
          Priority
        </label>
        <select
          id="priority-filter"
          className="select-dropdown"
          value={filters.priority}
          onChange={(e) => onChange({ priority: e.target.value as EventPriority | "" })}
        >
          <option value="">All Priorities</option>
          {EVENT_PRIORITIES.map((priority) => (
            <option key={priority} value={priority}>
              {priority}
            </option>
          ))}
        </select>
      </div>

      {/* Clear Filters Button */}
      {isFiltered && (
        <div className="filter-group clear-group">
          <button
            type="button"
            className="btn btn-secondary btn-reset-filters"
            onClick={onClear}
            aria-label="Reset all search filters"
          >
            Clear Filters
          </button>
        </div>
      )}
    </div>
  );
};
