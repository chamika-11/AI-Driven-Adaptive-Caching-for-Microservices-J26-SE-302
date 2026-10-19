// ─────────────────────────────────────────────────────────────────────────────
// MongoDB Atlas Connection Manager — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Centralized infrastructure module managing Mongoose connection lifecycle,
// timeouts, duplicate prevention, readiness checks, and graceful teardown.
//
// Architectural Principles:
//   - Strict adherence to Mongoose connection lifecycle APIs.
//   - Fast failure timeouts (5s server selection) to avoid hanging on Atlas unreachability.
//   - Zero credential leakage in logs, errors, or readiness endpoints.
//   - Dependency injection support for isolated Vitest unit testing without Atlas.
// ─────────────────────────────────────────────────────────────────────────────

import dns from "node:dns";
import mongoose from "mongoose";
import { sanitizeMongoUri, type ApiConfig } from "../../config/index.js";

export interface MongoConnectionOptions {
  uri?: string;
  serverSelectionTimeoutMS?: number;
  connectTimeoutMS?: number;
  socketTimeoutMS?: number;
  maxPoolSize?: number;
  minPoolSize?: number;
  autoIndex?: boolean;
}

export type ConnectionStateName =
  | "disconnected"
  | "connected"
  | "connecting"
  | "disconnecting"
  | "uninitialized";

export interface DatabaseState {
  readyState: number;
  status: ConnectionStateName;
  isConnected: boolean;
}

/**
 * Standard sanitized database error.
 * Strips any passwords, tokens, or raw URIs from error messages.
 */
export class DatabaseConnectionError extends Error {
  public readonly isOperational = true;
  public readonly originalCode?: string | number;

  constructor(message: string, originalError?: unknown) {
    const sanitizedMsg = sanitizeMongoUri(message);
    super(`Database connection failed: ${sanitizedMsg}`);
    this.name = "DatabaseConnectionError";

    if (originalError && typeof originalError === "object") {
      const err = originalError as Record<string, unknown>;
      if (err.code !== undefined) {
        this.originalCode = err.code as string | number;
      }
    }
  }
}

/** Maps Mongoose numeric readyState to human-readable status name */
export function readyStateToName(state: number): ConnectionStateName {
  switch (state) {
    case 0:
      return "disconnected";
    case 1:
      return "connected";
    case 2:
      return "connecting";
    case 3:
      return "disconnecting";
    default:
      return "uninitialized";
  }
}

// In-flight connection promise to prevent duplicate concurrent connection attempts
let connectingPromise: Promise<mongoose.Connection> | null = null;
let listenersRegistered = false;

/**
 * Registers one-time lifecycle loggers on the Mongoose connection.
 * All logs are guaranteed to be sanitized.
 */
function registerLifecycleListeners(conn: mongoose.Connection): void {
  if (listenersRegistered) {
    return;
  }
  listenersRegistered = true;

  conn.on("connected", () => {
    console.info("[MongoDB] Connection established successfully to MongoDB Atlas.");
  });

  conn.on("error", (err: unknown) => {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[MongoDB] Connection error occurred: ${sanitizeMongoUri(msg)}`);
  });

  conn.on("disconnected", () => {
    console.warn("[MongoDB] Disconnected from MongoDB Atlas.");
  });

  conn.on("reconnected", () => {
    console.info("[MongoDB] Reconnected to MongoDB Atlas.");
  });
}

/**
 * Connects to MongoDB Atlas using Mongoose.
 *
 * Enforces:
 *   - Duplicate connection prevention: returns existing connection if readyState === 1.
 *   - Concurrent connection deduplication: reuses in-flight promise if readyState === 2.
 *   - Explicit timeouts: avoids startup hangs if cloud cluster is unreachable.
 *   - Zero mock fallback: never silently falls back to in-memory DB when Atlas fails.
 *   - Dependency injection: supports passing a mock mongoose client for unit tests.
 */
export async function connectToDatabase(
  options: MongoConnectionOptions = {},
  client: typeof mongoose = mongoose
): Promise<mongoose.Connection> {
  const currentConn = client.connection;

  // 1. If already connected, reuse existing active connection
  if (currentConn.readyState === 1) {
    return currentConn;
  }

  // 2. If a connection attempt is currently in-flight, return the existing promise
  if (currentConn.readyState === 2 && connectingPromise) {
    return connectingPromise;
  }

  const uri = options.uri ?? process.env["MONGODB_URI"];
  if (!uri || uri.trim() === "") {
    throw new DatabaseConnectionError(
      "MONGODB_URI is not configured. A valid MongoDB connection string is required."
    );
  }

  registerLifecycleListeners(currentConn);

  const mongooseOptions: mongoose.ConnectOptions = {
    serverSelectionTimeoutMS: options.serverSelectionTimeoutMS ?? 5000,
    connectTimeoutMS: options.connectTimeoutMS ?? 10000,
    socketTimeoutMS: options.socketTimeoutMS ?? 45000,
    maxPoolSize: options.maxPoolSize ?? 10,
    minPoolSize: options.minPoolSize ?? 2,
    autoIndex: options.autoIndex ?? false, // Recommended false in production for performance
  };

  connectingPromise = (async () => {
    try {
      const sanitizedTarget = sanitizeMongoUri(uri);
      console.info(`[MongoDB] Initiating connection to Atlas cluster (${sanitizedTarget})...`);

      await client.connect(uri, mongooseOptions);
      return client.connection;
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : String(error);

      // Node c-ares DNS resolver on Windows can fail with ECONNREFUSED / ETIMEOUT
      // on SRV queries (_mongodb._tcp) when using local network DNS proxies.
      // If detected, fallback to public DNS resolvers (8.8.8.8, 1.1.1.1) and retry once.
      if (
        (errorMsg.includes("querySrv ECONNREFUSED") ||
          errorMsg.includes("querySrv ETIMEOUT")) &&
        typeof dns.setServers === "function"
      ) {
        console.warn(
          "[MongoDB] DNS SRV query failed with local resolver. Retrying with public DNS resolvers (8.8.8.8, 1.1.1.1)..."
        );
        try {
          dns.setServers(["8.8.8.8", "1.1.1.1"]);
          await client.connect(uri, mongooseOptions);
          return client.connection;
        } catch (retryError: unknown) {
          const retryMsg =
            retryError instanceof Error ? retryError.message : String(retryError);
          throw new DatabaseConnectionError(retryMsg, retryError);
        }
      }

      throw new DatabaseConnectionError(errorMsg, error);
    } finally {
      connectingPromise = null;
    }
  })();

  return connectingPromise;
}

/**
 * Gracefully disconnects from MongoDB Atlas.
 * Resolves safely if already disconnected.
 */
export async function disconnectFromDatabase(
  client: typeof mongoose = mongoose
): Promise<void> {
  connectingPromise = null;

  if (client.connection.readyState === 0) {
    return;
  }

  try {
    await client.disconnect();
    console.info("[MongoDB] Disconnected from MongoDB Atlas.");
  } catch (error: unknown) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error(`[MongoDB] Error during disconnect: ${sanitizeMongoUri(errorMsg)}`);
    throw new DatabaseConnectionError(errorMsg, error);
  }
}

/**
 * Checks whether the database connection is currently active (readyState === 1).
 */
export function isDatabaseConnected(client: typeof mongoose = mongoose): boolean {
  return client.connection.readyState === 1;
}

/**
 * Returns a safe diagnostic summary of the current database connection state.
 * Never includes credentials, hostnames, or internal connection details.
 */
export function getConnectionState(client: typeof mongoose = mongoose): DatabaseState {
  const readyState = client.connection.readyState;
  return {
    readyState,
    status: readyStateToName(readyState),
    isConnected: readyState === 1,
  };
}

/**
 * Helper to build MongoConnectionOptions from an ApiConfig object.
 */
export function buildMongoOptionsFromConfig(config: ApiConfig): MongoConnectionOptions {
  return {
    uri: config.MONGODB_URI,
    serverSelectionTimeoutMS: config.DB_SERVER_SELECTION_TIMEOUT_MS,
    connectTimeoutMS: config.DB_CONNECT_TIMEOUT_MS,
    socketTimeoutMS: config.DB_SOCKET_TIMEOUT_MS,
    maxPoolSize: config.DB_MAX_POOL_SIZE,
    minPoolSize: config.DB_MIN_POOL_SIZE,
    autoIndex: config.NODE_ENV !== "production",
  };
}
