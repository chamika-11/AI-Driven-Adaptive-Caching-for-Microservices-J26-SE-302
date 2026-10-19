// ─────────────────────────────────────────────────────────────────────────────
// Environment Configuration & Validation — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// This module parses, validates, and exposes backend environment variables.
// It guarantees that:
//   1. All required variables (especially MONGODB_URI) are strictly validated.
//   2. Raw connection strings or credentials are never leaked into error messages.
//   3. Configuration parsing is completely testable via dependency injection.
// ─────────────────────────────────────────────────────────────────────────────

import { z } from "zod";

/**
 * Redacts credentials (passwords, usernames) from MongoDB connection URIs
 * so they are never printed in logs, console output, or error traces.
 */
export function sanitizeMongoUri(uri?: string): string {
  if (!uri || typeof uri !== "string") {
    return "[UNDEFINED_OR_EMPTY_URI]";
  }

  // Matches mongodb:// or mongodb+srv:// with user:password credentials
  return uri.replace(
    /(mongodb(?:\+srv)?:\/\/)([^:@\s]+):([^@\s]+)@/i,
    "$1$2:****@"
  );
}

/**
 * Base Zod schema for environment variables.
 */
export const EnvironmentSchema = z.object({
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .default("development"),

  API_PORT: z.coerce
    .number()
    .int("API_PORT must be an integer")
    .positive("API_PORT must be a positive number")
    .default(4004),

  API_HOST: z.string().min(1).default("0.0.0.0"),

  MONGODB_URI: z
    .string({
      required_error: "MONGODB_URI is required for database connectivity",
      invalid_type_error: "MONGODB_URI must be a string",
    })
    .trim()
    .min(1, "MONGODB_URI cannot be empty")
    .refine(
      (val) => val.startsWith("mongodb://") || val.startsWith("mongodb+srv://"),
      {
        message:
          "MONGODB_URI must start with a valid MongoDB scheme ('mongodb://' or 'mongodb+srv://')",
      }
    ),

  LOG_LEVEL: z
    .enum(["error", "warn", "info", "http", "verbose", "debug", "silly"])
    .default("debug"),

  // Database timeouts & pool configurations
  DB_SERVER_SELECTION_TIMEOUT_MS: z.coerce
    .number()
    .int()
    .positive()
    .default(5000), // 5 seconds fail-fast for cloud Atlas

  DB_CONNECT_TIMEOUT_MS: z.coerce
    .number()
    .int()
    .positive()
    .default(10000), // 10 seconds initial socket connect

  DB_SOCKET_TIMEOUT_MS: z.coerce
    .number()
    .int()
    .positive()
    .default(45000), // 45 seconds idle socket timeout

  DB_MAX_POOL_SIZE: z.coerce.number().int().positive().default(10),

  DB_MIN_POOL_SIZE: z.coerce.number().int().nonnegative().default(2),

  GRACEFUL_SHUTDOWN_TIMEOUT_MS: z.coerce
    .number()
    .int()
    .positive()
    .default(10000), // 10s shutdown grace period
});

export type ApiConfig = z.infer<typeof EnvironmentSchema>;

export interface ParseConfigOptions {
  /** If false, MONGODB_URI is made optional (e.g. for pure HTTP or route unit tests) */
  requireDb?: boolean;
}

/**
 * Custom error thrown when configuration fails validation.
 * Redacts any sensitive values that might be present in validation issues.
 */
export class ConfigValidationError extends Error {
  public readonly issues: string[];

  constructor(issues: string[]) {
    super(
      `Configuration validation failed:\n  - ${issues.join("\n  - ")}`
    );
    this.name = "ConfigValidationError";
    this.issues = issues;
  }
}

/**
 * Parses and validates an environment object (defaults to process.env).
 * Throws ConfigValidationError with sanitized messages if invalid.
 */
export function parseEnvironmentConfig(
  env: NodeJS.ProcessEnv = process.env,
  options: ParseConfigOptions = { requireDb: true }
): ApiConfig {
  const schema = options.requireDb === false
    ? EnvironmentSchema.extend({
        MONGODB_URI: EnvironmentSchema.shape.MONGODB_URI.optional(),
      })
    : EnvironmentSchema;

  const result = schema.safeParse(env);

  if (!result.success) {
    const errorMessages = result.error.issues.map((issue) => {
      const field = issue.path.join(".");
      // Return safe message without echoing any raw value or secret
      return `${field}: ${issue.message}`;
    });
    throw new ConfigValidationError(errorMessages);
  }

  return result.data as ApiConfig;
}
