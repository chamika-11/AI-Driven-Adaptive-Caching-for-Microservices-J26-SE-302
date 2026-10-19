// ─────────────────────────────────────────────────────────────────────────────
// Centralized Express Error Handling Middleware — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Translates application, Zod, and repository errors into consistent,
// frontend-friendly JSON responses with zero credential or stack trace leakage.
// ─────────────────────────────────────────────────────────────────────────────

import type { Request, Response, NextFunction } from "express";
import { ZodError } from "zod";
import {
  RepositoryValidationError,
  RepositoryNotFoundError,
  RepositoryDuplicateKeyError,
  RepositoryDatabaseError,
} from "../repositories/index.js";
import { DatabaseConnectionError } from "../infrastructure/database/index.js";
import { HttpError } from "../errors/index.js";

export interface ApiErrorResponse {
  error: string;
  message: string;
  statusCode: number;
  issues?: string[];
  timestamp: string;
}

export function errorHandler(
  err: unknown,
  _req: Request,
  res: Response,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _next: NextFunction
): void {
  const timestamp = new Date().toISOString();

  // 1. Zod runtime validation error
  if (err instanceof ZodError) {
    const issues = err.issues.map((issue) => {
      const path = issue.path.join(".");
      return path ? `${path}: ${issue.message}` : issue.message;
    });

    const response: ApiErrorResponse = {
      error: "Bad Request",
      message: "Request validation failed",
      statusCode: 400,
      issues,
      timestamp,
    };
    res.status(400).json(response);
    return;
  }

  // 2. Repository validation error
  if (err instanceof RepositoryValidationError) {
    const response: ApiErrorResponse = {
      error: "Bad Request",
      message: err.message,
      statusCode: 400,
      issues: err.issues,
      timestamp,
    };
    res.status(400).json(response);
    return;
  }

  // 3. Not Found error
  if (err instanceof RepositoryNotFoundError) {
    const response: ApiErrorResponse = {
      error: "Not Found",
      message: err.message,
      statusCode: 404,
      timestamp,
    };
    res.status(404).json(response);
    return;
  }

  // 4. Duplicate Key / Conflict error
  if (err instanceof RepositoryDuplicateKeyError) {
    const response: ApiErrorResponse = {
      error: "Conflict",
      message: `An event with identifier '${err.value}' already exists`,
      statusCode: 409,
      timestamp,
    };
    res.status(409).json(response);
    return;
  }

  // 5. Explicit Domain HTTP errors
  if (err instanceof HttpError) {
    const errorNameMap: Record<number, string> = {
      400: "Bad Request",
      404: "Not Found",
      409: "Conflict",
      503: "Service Unavailable",
    };

    const response: ApiErrorResponse = {
      error: errorNameMap[err.statusCode] ?? "Error",
      message: err.message,
      statusCode: err.statusCode,
      issues: err.issues,
      timestamp,
    };
    res.status(err.statusCode).json(response);
    return;
  }

  // 6. Database Unavailable error
  if (err instanceof RepositoryDatabaseError || err instanceof DatabaseConnectionError) {
    console.error(`[API Error] Database unavailable: ${err.message}`);
    const response: ApiErrorResponse = {
      error: "Service Unavailable",
      message: "Database service is temporarily unavailable",
      statusCode: 503,
      timestamp,
    };
    res.status(503).json(response);
    return;
  }

  // 7. Express body-parser SyntaxError (e.g. malformed JSON in request body)
  if (
    err instanceof SyntaxError &&
    "status" in err &&
    (err as Record<string, unknown>)["status"] === 400
  ) {
    const response: ApiErrorResponse = {
      error: "Bad Request",
      message: "Malformed JSON payload in request body",
      statusCode: 400,
      timestamp,
    };
    res.status(400).json(response);
    return;
  }

  // 8. Unhandled Internal Server Error (Never expose credentials, URI or internal stack)
  console.error("[API Error] Unhandled internal error:", err);
  const response: ApiErrorResponse = {
    error: "Internal Server Error",
    message: "An unexpected internal server error occurred",
    statusCode: 500,
    timestamp,
  };
  res.status(500).json(response);
}
