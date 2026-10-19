# API Documentation Ingestion Service (Component 4)

FastAPI microservice for ingesting OpenAPI 3.x and Swagger 2.0 specifications, validating structural boundaries, and extracting normalized service endpoints for downstream Event Intelligence & Context-Aware Feature Engineering.

## Capabilities

- **Supported Specifications:**
  - OpenAPI 3.0.x and 3.1.x (JSON & YAML)
  - Swagger 2.0 (JSON & YAML)
- **Security & Safety Guardrails:**
  - Safe YAML parsing (`yaml.safe_load`) prevents arbitrary Python object construction.
  - Zero remote `$ref` fetching prevents Server-Side Request Forgery (SSRF) and external network dependencies.
  - Configurable maximum upload size limits (default: 5 MB).
  - Deterministic SHA-256 provenance tracking for each document.
  - Internal schema references (`#/components/schemas/...` and `#/definitions/...`) parsed without external resolution.
- **Normalized Output:**
  - Microservice metadata (title, version, service name, server/base URLs).
  - Separate extraction of multiple HTTP operations per path.
  - Detailed parameter locations (`path`, `query`, `header`, `cookie`), types, and requirements.
  - Request body schemas and response status code mappings.

## Environment Variables

Copy `.env.example` to `.env`:

```env
PORT=8001
HOST=0.0.0.0
MAX_UPLOAD_SIZE_BYTES=5242880
LOG_LEVEL=INFO
# Optional: MongoDB Atlas URI. If omitted, uses InMemoryDocumentRepository
MONGODB_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/
DATABASE_NAME=component4
```

## Setup & Virtual Environment

1. Ensure Python 3.12+ is installed.
2. Initialize virtual environment (Note: on Windows where the project folder path is deep, place the venv in `%USERPROFILE%\.c4_venv` to prevent Windows `MAX_PATH` 260-char overflow):
   ```bash
   python -m virtualenv "%USERPROFILE%\.c4_venv"
   "%USERPROFILE%\.c4_venv\Scripts\pip.exe" install -r requirements.txt
   ```

## Running the Service

You can start the service directly from the monorepo root:

```bash
npm run dev:ingestion
```

Or from `services/ingestion/`:

```bash
"%USERPROFILE%\.c4_venv\Scripts\python.exe" -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

- API Interactive Docs (Swagger UI): `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- Health check: `http://localhost:8001/health`

## Running Automated Tests

Run the comprehensive pytest suite:

```bash
pytest -v
```

## Sample Ingestion Request

```bash
curl -X POST "http://localhost:8001/api/v1/ingest" \
  -H "Accept: application/json" \
  -F "file=@tests/fixtures/valid_openapi3.json"
```
