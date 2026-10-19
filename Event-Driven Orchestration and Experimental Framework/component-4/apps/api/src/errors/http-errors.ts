// ─────────────────────────────────────────────────────────────────────────────
// HTTP Domain Errors — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Typed HTTP error classes with status codes and safe client messaging.
// ─────────────────────────────────────────────────────────────────────────────

export class HttpError extends Error {
  public readonly statusCode: number;
  public readonly isOperational: boolean;
  public readonly issues?: string[];

  constructor(statusCode: number, message: string, issues?: string[]) {
    super(message);
    this.name = "HttpError";
    this.statusCode = statusCode;
    this.isOperational = true;
    this.issues = issues;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class BadRequestError extends HttpError {
  constructor(message = "Bad Request", issues?: string[]) {
    super(400, message, issues);
    this.name = "BadRequestError";
  }
}

export class NotFoundError extends HttpError {
  constructor(message = "Resource not found") {
    super(404, message);
    this.name = "NotFoundError";
  }
}

export class ConflictError extends HttpError {
  constructor(message = "Resource conflict") {
    super(409, message);
    this.name = "ConflictError";
  }
}

export class ServiceUnavailableError extends HttpError {
  constructor(message = "Service temporarily unavailable") {
    super(503, message);
    this.name = "ServiceUnavailableError";
  }
}
