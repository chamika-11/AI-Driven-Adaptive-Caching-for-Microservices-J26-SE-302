# Component 4 — Event Intelligence & Context-Aware Feature Engineering

Part of the **AI-Based Adaptive Caching for Mitigating Data Communication Overhead in Microservice Architectures** research project.

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
| `npm run test:api`    | Run API tests only                          |

---

## Workspaces

| Package              | Location           | Purpose                                    |
| -------------------- | ------------------ | ------------------------------------------ |
| `@component4/api`    | `apps/api/`        | Express API server (health-check scaffold)  |
| `@component4/web`    | `apps/web/`        | React + Vite dashboard (health-check UI)    |
| `@component4/shared` | `packages/shared/` | Shared TypeScript types and data contracts  |

---

## Testing

```bash
# Run all tests
npm run test

# Run API tests only
npm run test:api
```

Tests use [Vitest](https://vitest.dev/). The API test suite uses [supertest](https://github.com/ladjs/supertest) for HTTP assertions without starting a server.

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
