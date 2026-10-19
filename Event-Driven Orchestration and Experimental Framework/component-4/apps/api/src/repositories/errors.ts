// ─────────────────────────────────────────────────────────────────────────────
// Event Repository Errors — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Strongly-typed, HTTP-independent repository error hierarchy.
// These errors encapsulate data access and validation failures without
// exposing raw MongoDB drivers, stack traces, credentials, or internal schemas.
// ─────────────────────────────────────────────────────────────────────────────

import { sanitizeMongoUri } from "../config/index.js";

/**
 * Base abstract repository error.
 */
export class RepositoryError extends Error {
  public readonly isOperational = true;

  constructor(message: string) {
    super(sanitizeMongoUri(message));
    this.name = "RepositoryError";
  }
}

/**
 * Thrown when an input payload fails schema or business validation constraints.
 */
export class RepositoryValidationError extends RepositoryError {
  public readonly issues: string[];

  constructor(message: string, issues: string[] = []) {
    super(message);
    this.name = "RepositoryValidationError";
    this.issues = issues.map((i) => sanitizeMongoUri(i));
  }
}

/**
 * Thrown when an event cannot be located by its application-level eventId.
 */
export class RepositoryNotFoundError extends RepositoryError {
  public readonly eventId: string;

  constructor(eventId: string) {
    super(`Scheduled event with ID '${eventId}' was not found.`);
    this.name = "RepositoryNotFoundError";
    this.eventId = eventId;
  }
}

/**
 * Thrown when a unique key constraint is violated (e.g. duplicate eventId).
 */
export class RepositoryDuplicateKeyError extends RepositoryError {
  public readonly key: string;
  public readonly value: string;

  constructor(key: string, value: string) {
    super(`Duplicate key violation: ${key} '${value}' already exists.`);
    this.name = "RepositoryDuplicateKeyError";
    this.key = key;
    this.value = value;
  }
}

/**
 * Thrown when an underlying MongoDB driver or connectivity failure occurs.
 */
export class RepositoryDatabaseError extends RepositoryError {
  constructor(message: string) {
    super(`Database persistence error: ${message}`);
    this.name = "RepositoryDatabaseError";
  }
}
