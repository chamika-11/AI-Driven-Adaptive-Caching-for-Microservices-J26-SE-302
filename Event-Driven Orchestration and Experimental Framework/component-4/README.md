# Component 4 — Event Intelligence & Context-Aware Feature Engineering

Part of the **AI-Based Adaptive Caching for Mitigating Data Communication Overhead in Microservice Architectures** research project.

> [!IMPORTANT]
> **Complete Technical Specification & Code Definitions:**  
> For the comprehensive final report including every code file definition, architecture diagrams, Mongoose persistence models, REST API endpoints, React 19 dashboard, and test suite breakdowns up to Phase 3.3, see **[final.md](final.md)**.

---

## Prerequisites

| Tool    | Minimum Version | Check           |
| ------- | --------------- | --------------- |
| Node.js | 20.x            | `node --version` |
| npm     | 10.x            | `npm --version`  |

> **Note:** MongoDB is **not** required for the initial scaffold (Phase 1.1). It will be introduced in a later phase.

---

## Project Structure

```
component-4/
├── apps/
│   ├── api/          # Express backend (TypeScript)
│   └── web/          # React + Vite frontend (TypeScript)
├── packages/
│   └── shared/       # Shared types, schemas, and data contracts
├── docs/             # Architecture docs and decision records
├── .env.example      # Safe example environment variables
├── .gitignore
├── tsconfig.base.json
├── package.json      # npm workspaces root
└── README.md
```

---

## Quick Start

### 1. Clone and navigate

```bash
git clone <repository-url>
cd "Event-Driven Orchestration and Experimental Framework/component-4"
```

### 2. Install dependencies

```bash
npm install
```

### 3. Environment variables

```bash
cp .env.example .env      # Linux / macOS
copy .env.example .env     # Windows
```

Edit `.env` as needed. See [`.env.example`](.env.example) for available variables.

### 4. Build the shared package

The backend and frontend both depend on the shared package. Build it first:

```bash
npm run build:shared
```

### 5. Start the backend API (dev mode)

```bash
npm run dev:api
```

The API will be available at **http://localhost:4004**.

Verify with:
```bash
curl http://localhost:4004/api/health
# or in PowerShell:
Invoke-RestMethod http://localhost:4004/api/health
```

Expected response:
```json
{
  "status": "ok",
  "component": "component-4-api",
  "version": "0.1.0",
  "timestamp": "2026-10-15T09:27:02.956Z"
}
```

### 6. Start the frontend (dev mode)

In a second terminal:

```bash
npm run dev:web
```

The frontend will be available at **http://localhost:5173**. The Vite dev server proxies `/api` requests to the backend.

---

## Scripts

All scripts can be run from the monorepo root:

| Script                | Description                                 |
| --------------------- | ------------------------------------------- |
| `npm run dev:api`     | Start the API in development mode (tsx watch) |
| `npm run dev:web`     | Start the frontend Vite dev server          |
| `npm run build:shared`| Build the shared types package              |
| `npm run build:api`   | Compile the API to JavaScript               |
| `npm run build:web`   | Type-check and bundle the frontend          |
| `npm run build`       | Build all workspaces (shared → api → web)   |
| `npm run test`        | Run tests across all workspaces             |
| `npm run test:api`    | Run API tests only (unit + Atlas integration)|
| `npm run test:shared` | Run shared package schema & fixture tests   |

---

## Frontend Dashboard Foundation (Part 3.2)

The frontend is an enterprise-grade React 18 + TypeScript single-page application built with Vite in `apps/web/`. It connects to Component 4's Event Management REST API and MongoDB Atlas backend.

### Environment Configuration

Configure `apps/web/.env` using [`apps/web/.env.example`](apps/web/.env.example):

```bash
# Optional: backend API URL (defaults to empty string in development to use Vite's proxy)
VITE_API_BASE_URL=http://localhost:4004
```

- **In Development:** Leave unset or empty. The Vite dev server proxies all `/api/*` requests directly to `http://localhost:4004`.
- **In Production / Custom Staging:** Set `VITE_API_BASE_URL` to the publicly accessible API origin (e.g., `https://api.example.com`).

### Endpoints Used

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/events` | `GET` | Fetches paginated scheduled events (`page`, `limit`, `status`, `eventType`, `priority`, `sortBy`, `sortOrder`). |
| `/api/events` | `GET` (limit=1) | Retrieves exact server-side summary totals per status (`SCHEDULED`, `PROCESSING`, `COMPLETED`, `CANCELLED`). |
| `/api/health/ready` | `GET` | Live readiness probe verifying process state and MongoDB Atlas connectivity. |

### Architectural Limitations & Solutions

- **Status Aggregates:** The backend does not currently expose a dedicated `/api/events/summary` endpoint. Rather than computing misleading counts from only the current page (10 records), the frontend fires parallel, lightweight `limit: 1` status-filtered queries to read the exact server-calculated `pagination.total`.
- **Search Scope:** The backend supports strict filtering on `status`, `eventType`, and `priority`. Full-text search across arbitrary event names is currently performed client-side on the loaded page records, and is accompanied by an explicit feedback banner informing the user.

---

## Create and Edit Events (Part 3.3)

Part 3.3 adds dynamic mutation capabilities to the Event Management Dashboard via an accessible modal dialog:

### Opening the Forms
- **Create Event:** Click the **"+ Create Event"** primary button located in the dashboard panel header row above the filter bar.
- **Edit Event:** Click the **"Edit"** button located in the `Actions` column of any scheduled event row in the table.

### Event Fields & Contract Rules

| Field | Input Control | Required | Validation Rules |
| --- | --- | --- | --- |
| `eventName` | Text input | **Yes** | 1–200 characters after whitespace trimming. |
| `eventType` | Select dropdown | **Yes** | One of `RESULT_RELEASE`, `REGISTRATION`, `FLASH_SALE`, `TICKET_RELEASE`, `PROMOTIONAL_CAMPAIGN`, `PAYMENT_DEADLINE`, `OTHER`. |
| `startTime` | `datetime-local` | **Yes** | Valid date/time; transmitted as ISO 8601 with explicit offset. |
| `endTime` | `datetime-local` | **Yes** | Valid date/time; must be strictly later than `startTime`. |
| `prewarmWindowMinutes` | Numeric input | **Yes** | Non-negative integer between `0` and `10080` (7 days maximum). Default: `30`. |
| `expectedLoad` | Select dropdown | No | One of `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH`, `UNKNOWN`. |
| `priority` | Select dropdown | No | One of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `description` | Textarea | No | Up to 2,000 characters. |
| `eventId`, `status`, `createdAt`, `updatedAt` | None | **No** | System-managed. Excluded from edit payloads and immutable by client. |

### Timezone Transparency & Invariant Handling
- **Local Interpretation:** Date/time pickers display values in the user's local operating system timezone. The modal explicitly announces the active local timezone (e.g. `Asia/Colombo (UTC+05:30)`).
- **ISO Transmission:** Input values are converted to standard ISO 8601 strings with explicit timezone offsets (e.g., `2026-11-20T09:00:00+05:30`). No trailing `Z` is appended unless the local offset is genuinely UTC (`0`).
- **Partial Update Date Safety:** When editing an event and updating only `startTime` or only `endTime`, the form verifies the resulting merged window against the existing record before sending PATCH requests.

### Form Validation & Error Handling
- **Client-Side:** Enforced using shared runtime schemas (`CreateScheduledEventInputSchema`, `UpdateScheduledEventInputSchema`).
- **Server-Side:** If the backend rejects a mutation (HTTP 400), specific issues are mapped to the affected fields, and a prominent alert banner summarizes backend validation feedback without discarding user inputs.
- **Success & Refresh:** Upon confirmed server creation or update, the modal automatically closes, an accessible toast notification appears (`role="status"`), and the dashboard table and summary cards immediately reload with fresh data.

---

## Testing

```bash
# Run all tests across workspaces (shared, api, web)
npm run test

# Run frontend dashboard tests only
npm run test --workspace=apps/web

# Run API tests only
npm run test:api

# Run shared schema and fixture tests only
npm run test:shared
```

Tests use [Vitest](https://vitest.dev/).
- Frontend tests use `@testing-library/react` with `happy-dom` and mock fetch fixtures from `@component4/shared`.
- API tests use `supertest` for route validation and live MongoDB Atlas integration suites.

---

## Technology Stack

- **Runtime:** Node.js 24.x
- **Language:** TypeScript 5.6
- **Backend:** Express 4.x, Zod, Helmet, CORS, dotenv
- **Frontend:** React 18, Vite 5
- **Testing:** Vitest, supertest
- **Package Manager:** npm 11.x (workspaces)

---

## What's Next

This scaffold covers **Phase 1.1** only. Upcoming phases include:

- Event Management API and MongoDB integration
- Calendar ingestion and validation
- API Knowledge Repository
- RAG-based Event Intelligence
- Event Scheduler and prewarm-window detection
- Feature Engineering Pipeline
- Component 3 integration
