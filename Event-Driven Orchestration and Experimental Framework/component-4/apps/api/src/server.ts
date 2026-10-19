// ─────────────────────────────────────────────────────────────────────────────
// Server Lifecycle & Graceful Shutdown — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Manages:
//   1. Predictable backend startup sequence (Config -> MongoDB -> HTTP).
//   2. Graceful shutdown on SIGINT / SIGTERM with in-flight drain & DB disconnect.
//   3. Duplicate shutdown prevention.
//   4. Separation of server listener from Express app instance for testability.
// ─────────────────────────────────────────────────────────────────────────────

import http from "node:http";
import { app } from "./app.js";
import {
  parseEnvironmentConfig,
  sanitizeMongoUri,
  type ApiConfig,
} from "./config/index.js";
import {
  connectToDatabase,
  disconnectFromDatabase,
  buildMongoOptionsFromConfig,
} from "./infrastructure/database/index.js";

export interface ServerInstance {
  server: http.Server;
  config: ApiConfig;
  shutdown: (signal?: string) => Promise<void>;
}

export interface ShutdownOptions {
  timeoutMs?: number;
  onExit?: (code: number) => void;
}

export interface ServerStartupOptions {
  env?: NodeJS.ProcessEnv;
  config?: ApiConfig;
  connectDb?: (config: ApiConfig) => Promise<unknown>;
  disconnectDb?: () => Promise<void>;
  registerSignals?: boolean;
}

/**
 * Creates an idempotent, testable graceful shutdown handler.
 * Guarantees in-flight HTTP drain, database disconnection, and timeout protection.
 */
export function createGracefulShutdownHandler(
  server: http.Server,
  disconnectDb: () => Promise<void> = disconnectFromDatabase,
  options: ShutdownOptions = {}
): (signal?: string) => Promise<void> {
  const timeoutMs = options.timeoutMs ?? 10000;
  const exitFn = options.onExit ?? ((code) => process.exit(code));
  let isShuttingDown = false;

  return async (signal: string = "SIGTERM"): Promise<void> => {
    if (isShuttingDown) {
      console.warn(`[Shutdown] Shutdown already in progress. Ignoring duplicate signal (${signal}).`);
      return;
    }
    isShuttingDown = true;
    console.info(`[Shutdown] Received ${signal}. Commencing graceful shutdown...`);

    // Safety watchdog: force termination if cleanup hangs beyond timeout
    const forceTimer = setTimeout(() => {
      console.error(
        `[Shutdown] Graceful shutdown timed out after ${timeoutMs}ms. Forcing exit.`
      );
      exitFn(1);
    }, timeoutMs);

    // Unref timer so it doesn't keep the event loop alive if cleanup finishes quickly
    if (typeof forceTimer.unref === "function") {
      forceTimer.unref();
    }

    try {
      // Step 1: Stop accepting new HTTP connections and drain in-flight requests
      await new Promise<void>((resolve, reject) => {
        server.close((err) => {
          if (err) {
            console.error(`[Shutdown] Error while closing HTTP server: ${err.message}`);
            return reject(err);
          }
          console.info("[Shutdown] HTTP server closed successfully; no new connections accepted.");
          resolve();
        });
      });

      // Step 2: Gracefully close MongoDB Atlas connection
      await disconnectDb();
      console.info("[Shutdown] Database connection closed successfully.");

      clearTimeout(forceTimer);
      console.info("[Shutdown] Graceful shutdown completed cleanly.");
      exitFn(0);
    } catch (error: unknown) {
      clearTimeout(forceTimer);
      const msg = error instanceof Error ? error.message : String(error);
      console.error(`[Shutdown] Error occurred during shutdown: ${sanitizeMongoUri(msg)}`);
      exitFn(1);
    }
  };
}

let signalsRegistered = false;

/**
 * Executes the predictable backend startup sequence:
 *   1. Load and validate environment configuration.
 *   2. Establish MongoDB Atlas connection.
 *   3. Start listening for HTTP requests on configured host & port.
 *   4. Register SIGINT & SIGTERM graceful shutdown hooks.
 */
export async function startServer(
  options: ServerStartupOptions = {}
): Promise<ServerInstance> {
  try {
    // Step 1: Load and validate configuration
    const config =
      options.config ??
      parseEnvironmentConfig(options.env ?? process.env, { requireDb: true });

    const connectFn =
      options.connectDb ??
      ((cfg) => connectToDatabase(buildMongoOptionsFromConfig(cfg)));

    const disconnectFn = options.disconnectDb ?? disconnectFromDatabase;

    // Step 2: Connect to MongoDB Atlas first
    console.info("[Startup] Connecting to MongoDB Atlas...");
    await connectFn(config);

    // Step 3: Start HTTP listener only after database connection succeeds
    const server = http.createServer(app);

    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(config.API_PORT, config.API_HOST, () => {
        server.removeListener("error", reject);
        console.info(
          `[Component 4 API] listening on http://${config.API_HOST}:${config.API_PORT} [Env: ${config.NODE_ENV}]`
        );
        resolve();
      });
    });

    // Step 4: Register graceful shutdown handler
    const shutdownHandler = createGracefulShutdownHandler(server, disconnectFn, {
      timeoutMs: config.GRACEFUL_SHUTDOWN_TIMEOUT_MS,
    });

    const shouldRegisterSignals = options.registerSignals ?? (config.NODE_ENV !== "test");
    if (shouldRegisterSignals && !signalsRegistered) {
      signalsRegistered = true;
      process.on("SIGINT", () => {
        void shutdownHandler("SIGINT");
      });
      process.on("SIGTERM", () => {
        void shutdownHandler("SIGTERM");
      });
    }

    return {
      server,
      config,
      shutdown: shutdownHandler,
    };
  } catch (error: unknown) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error(`[Startup Error] Backend startup failed: ${sanitizeMongoUri(errorMsg)}`);
    throw error;
  }
}
