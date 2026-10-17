/**
 * @component4/shared
 *
 * Shared types, schemas, and data contracts for Component 4:
 * "Event Intelligence & Context-Aware Feature Engineering"
 *
 * This package will eventually contain:
 *   - Zod schemas for event payloads, calendar data, and API knowledge entries
 *   - Shared TypeScript interfaces and enums
 *   - Data contracts between the API and the frontend
 *   - Constants and configuration types shared across workspaces
 */

// ── Health-check contract (used by both API and Web) ─────────────────────────

export interface HealthCheckResponse {
  status: "ok" | "degraded" | "error";
  component: string;
  version: string;
  timestamp: string;
}

// ── Placeholder namespace — expanded in later phases ─────────────────────────

export const COMPONENT_NAME = "Event Intelligence & Context-Aware Feature Engineering" as const;
export const COMPONENT_ID = "component-4" as const;
