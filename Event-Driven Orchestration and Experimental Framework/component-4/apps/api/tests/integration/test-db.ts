// ─────────────────────────────────────────────────────────────────────────────
// Test Database Infrastructure & Safety Guardrails — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Ensures:
//   1. Destructive operations NEVER target development, staging, or production DBs.
//   2. Database name MUST strictly match 'component4_test' or end with '_test'.
//   3. Credentials and URIs are NEVER logged or leaked.
//   4. Graceful skipping when test database configuration is absent.
// ─────────────────────────────────────────────────────────────────────────────

import "dotenv/config";
import dns from "node:dns";
import mongoose from "mongoose";
import { ScheduledEventModel } from "../../src/models/index.js";
import {
  connectToDatabase,
  disconnectFromDatabase,
} from "../../src/infrastructure/database/index.js";

/**
 * Forbidden database names that must NEVER be used for integration testing.
 */
const FORBIDDEN_DB_NAMES = new Set([
  "admin",
  "local",
  "config",
  "event_intelligence",
  "production",
  "prod",
  "development",
  "dev",
  "default",
]);

export interface TestDbValidationResult {
  isValid: boolean;
  dbName: string;
  error?: string;
}

/**
 * Extracts and strictly validates the database name from a MongoDB URI.
 * Guarantees that only isolated test databases (e.g. 'component4_test') can be targeted.
 */
export function validateTestDatabase(uri: string): TestDbValidationResult {
  try {
    const url = new URL(uri);
    const rawPath = url.pathname.replace(/^\//, "").trim();
    const dbName = rawPath.split("?")[0].trim();

    if (!dbName) {
      return {
        isValid: false,
        dbName: "",
        error: "Target database name is missing from URI. A dedicated test database name is required.",
      };
    }

    const lower = dbName.toLowerCase();

    if (FORBIDDEN_DB_NAMES.has(lower)) {
      return {
        isValid: false,
        dbName,
        error: `Database '${dbName}' is a forbidden/production database name. Integration tests must use an isolated test database.`,
      };
    }

    if (lower !== "component4_test" && !lower.endsWith("_test")) {
      return {
        isValid: false,
        dbName,
        error: `Database '${dbName}' does not follow the required test naming convention (must be 'component4_test' or end with '_test').`,
      };
    }

    return { isValid: true, dbName };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      isValid: false,
      dbName: "",
      error: `Invalid connection URI syntax: ${msg}`,
    };
  }
}

/**
 * Returns the validated test database URI if configured and safe.
 * Returns null if not configured or disabled.
 * Throws an Error if configured to an unsafe database name.
 */
export function getSafeTestDatabaseUri(): string | null {
  const testUri = process.env["MONGODB_TEST_URI"];
  if (!testUri || testUri.trim() === "" || testUri.includes("<db_username>")) {
    return null;
  }

  const validation = validateTestDatabase(testUri);
  if (!validation.isValid) {
    throw new Error(
      `[SECURITY ERROR] MONGODB_TEST_URI safety validation failed: ${validation.error}`
    );
  }

  return testUri;
}

/**
 * Determines whether live Atlas integration tests should execute.
 */
export function isLiveIntegrationEnabled(): boolean {
  if (process.env["TEST_LIVE_ATLAS"] !== "true") {
    return false;
  }

  const testUri = getSafeTestDatabaseUri();
  return Boolean(testUri);
}

/**
 * Connects to the isolated test database and ensures indexes are built.
 */
export async function setupIntegrationDatabase(): Promise<mongoose.Connection> {
  const uri = getSafeTestDatabaseUri();
  if (!uri) {
    throw new Error(
      "Cannot setup integration database: MONGODB_TEST_URI is not configured."
    );
  }

  // Windows c-ares local DNS fallback
  if (typeof dns.setServers === "function") {
    dns.setServers(["8.8.8.8", "1.1.1.1"]);
  }

  const conn = await connectToDatabase({
    uri,
    serverSelectionTimeoutMS: 15000,
    connectTimeoutMS: 15000,
    socketTimeoutMS: 45000,
    autoIndex: true,
  });

  const validation = validateTestDatabase(uri);
  if (conn.name !== validation.dbName) {
    await disconnectFromDatabase();
    throw new Error(
      `[SECURITY ERROR] Connected database name '${conn.name}' does not match validated test database '${validation.dbName}'. Disconnecting immediately.`
    );
  }

  // Explicitly ensure unique and compound indexes are created in Atlas before running tests
  await ScheduledEventModel.createIndexes();

  return conn;
}

/**
 * Cleans the scheduled_events collection only within the verified test database.
 */
export async function cleanTestDatabase(): Promise<void> {
  if (mongoose.connection.readyState !== 1) {
    return;
  }

  const dbName = mongoose.connection.name;
  if (dbName !== "component4_test" && !dbName.endsWith("_test")) {
    throw new Error(
      `[SECURITY ERROR] Refusing to clean database '${dbName}' as it is not a verified test database.`
    );
  }

  await ScheduledEventModel.deleteMany({});
}

/**
 * Cleans test data and gracefully closes the database connection.
 */
export async function teardownIntegrationDatabase(): Promise<void> {
  try {
    await cleanTestDatabase();
  } catch {
    // Continue disconnect even if clean encounters an issue
  } finally {
    await disconnectFromDatabase();
  }
}
