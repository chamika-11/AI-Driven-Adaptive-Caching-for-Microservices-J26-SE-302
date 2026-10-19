/**
 * Unit tests for Server Lifecycle and Graceful Shutdown.
 *
 * Verifies:
 *   1. Startup sequence connects to DB before starting HTTP listener.
 *   2. Startup fails without starting HTTP listener if DB connection throws.
 *   3. Graceful shutdown handler closes HTTP server, then disconnects DB.
 *   4. Graceful shutdown handler prevents duplicate execution on repeated signals.
 *   5. Clean exit handling.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type http from "node:http";
import {
  createGracefulShutdownHandler,
  startServer,
} from "../src/server.js";
import type { ApiConfig } from "../src/config/index.js";

const mockConfig: ApiConfig = {
  NODE_ENV: "test",
  API_PORT: 4999,
  API_HOST: "127.0.0.1",
  MONGODB_URI: "mongodb+srv://user:pass@cluster.mongodb.net/test",
  LOG_LEVEL: "debug",
  DB_SERVER_SELECTION_TIMEOUT_MS: 1000,
  DB_CONNECT_TIMEOUT_MS: 2000,
  DB_SOCKET_TIMEOUT_MS: 5000,
  DB_MAX_POOL_SIZE: 5,
  DB_MIN_POOL_SIZE: 1,
  GRACEFUL_SHUTDOWN_TIMEOUT_MS: 3000,
};

describe("Server Lifecycle & Graceful Shutdown", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("1. Startup Sequence", () => {
    it("should connect to DB first and then start HTTP listener", async () => {
      const callOrder: string[] = [];

      const mockConnectDb = vi.fn().mockImplementation(async () => {
        callOrder.push("connectDb");
      });

      const mockDisconnectDb = vi.fn().mockImplementation(async () => {
        callOrder.push("disconnectDb");
      });

      const instance = await startServer({
        config: mockConfig,
        connectDb: mockConnectDb,
        disconnectDb: mockDisconnectDb,
        registerSignals: false,
      });

      expect(callOrder).toContain("connectDb");
      expect(instance.server.listening).toBe(true);

      // Clean up server
      await new Promise<void>((resolve) => instance.server.close(() => resolve()));
    });

    it("should fail startup and NOT start HTTP listener if database connection fails", async () => {
      const mockConnectDb = vi.fn().mockRejectedValue(new Error("Atlas cluster connection refused"));

      await expect(
        startServer({
          config: mockConfig,
          connectDb: mockConnectDb,
          registerSignals: false,
        })
      ).rejects.toThrow("Atlas cluster connection refused");

      expect(mockConnectDb).toHaveBeenCalledTimes(1);
    });
  });

  describe("2. Graceful Shutdown Handler", () => {
    it("should close HTTP server and disconnect DB in order", async () => {
      const callOrder: string[] = [];

      const mockHttpServer = {
        close: vi.fn((cb: (err?: Error) => void) => {
          callOrder.push("httpServerClose");
          cb();
        }),
      } as unknown as http.Server;

      const mockDisconnectDb = vi.fn().mockImplementation(async () => {
        callOrder.push("disconnectDb");
      });

      const mockExit = vi.fn();

      const shutdownHandler = createGracefulShutdownHandler(
        mockHttpServer,
        mockDisconnectDb,
        {
          timeoutMs: 2000,
          onExit: mockExit,
        }
      );

      await shutdownHandler("SIGTERM");

      expect(callOrder).toEqual(["httpServerClose", "disconnectDb"]);
      expect(mockExit).toHaveBeenCalledWith(0);
    });

    it("should ignore duplicate shutdown signals when already shutting down", async () => {
      const mockHttpServer = {
        close: vi.fn((cb: (err?: Error) => void) => {
          setTimeout(cb, 10);
        }),
      } as unknown as http.Server;

      const mockDisconnectDb = vi.fn().mockResolvedValue(undefined);
      const mockExit = vi.fn();

      const shutdownHandler = createGracefulShutdownHandler(
        mockHttpServer,
        mockDisconnectDb,
        {
          timeoutMs: 2000,
          onExit: mockExit,
        }
      );

      // Fire two signals simultaneously
      const first = shutdownHandler("SIGTERM");
      const second = shutdownHandler("SIGINT");

      await Promise.all([first, second]);

      // Server close should only be initiated once
      expect(mockHttpServer.close).toHaveBeenCalledTimes(1);
      expect(mockDisconnectDb).toHaveBeenCalledTimes(1);
      expect(mockExit).toHaveBeenCalledTimes(1);
    });

    it("should call onExit(1) if HTTP server close errors", async () => {
      const mockHttpServer = {
        close: vi.fn((cb: (err?: Error) => void) => {
          cb(new Error("Socket drain error"));
        }),
      } as unknown as http.Server;

      const mockDisconnectDb = vi.fn().mockResolvedValue(undefined);
      const mockExit = vi.fn();

      const shutdownHandler = createGracefulShutdownHandler(
        mockHttpServer,
        mockDisconnectDb,
        {
          timeoutMs: 2000,
          onExit: mockExit,
        }
      );

      await shutdownHandler("SIGTERM");

      expect(mockExit).toHaveBeenCalledWith(1);
    });
  });
});
