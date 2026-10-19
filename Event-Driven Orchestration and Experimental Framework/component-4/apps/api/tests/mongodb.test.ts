/**
 * Unit tests for MongoDB/Mongoose Connection Manager.
 *
 * Verifies:
 *   1. Successful connection establishment with configured timeouts.
 *   2. Graceful error handling on connection failure without credential leakage.
 *   3. Prevention of duplicate connection attempts.
 *   4. Deduplication of in-flight connection promises.
 *   5. Disconnection behavior when connected and when already disconnected.
 *   6. Readiness queries and state mapping.
 *
 * Uses isolated mock clients via dependency injection so no network or Atlas
 * connection is attempted during unit test execution.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type mongoose from "mongoose";
import {
  connectToDatabase,
  disconnectFromDatabase,
  isDatabaseConnected,
  getConnectionState,
  readyStateToName,
  DatabaseConnectionError,
} from "../src/infrastructure/database/index.js";

function createMockMongoose(initialReadyState = 0) {
  const listeners: Record<string, ((...args: unknown[]) => void)[]> = {};

  const connection = {
    readyState: initialReadyState,
    on: vi.fn((event: string, callback: (...args: unknown[]) => void) => {
      listeners[event] = listeners[event] ?? [];
      listeners[event].push(callback);
    }),
    emit: (event: string, ...args: unknown[]) => {
      (listeners[event] ?? []).forEach((cb) => cb(...args));
    },
  };

  const connect = vi.fn().mockImplementation(async () => {
    connection.readyState = 1; // Mark connected
    connection.emit("connected");
    return connection;
  });

  const disconnect = vi.fn().mockImplementation(async () => {
    connection.readyState = 0; // Mark disconnected
    connection.emit("disconnected");
  });

  return {
    connection: connection as unknown as mongoose.Connection,
    connect: connect as unknown as typeof mongoose.connect,
    disconnect: disconnect as unknown as typeof mongoose.disconnect,
  } as unknown as typeof mongoose;
}

describe("MongoDB Connection Manager", () => {
  const dummyUri = "mongodb+srv://testuser:SecretPass123@cluster0.test.mongodb.net/testdb";

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("1. Connection Success & Options", () => {
    it("should connect with default Atlas-compatible timeout options", async () => {
      const mockClient = createMockMongoose(0);

      const conn = await connectToDatabase(
        {
          uri: dummyUri,
          serverSelectionTimeoutMS: 5000,
          connectTimeoutMS: 10000,
        },
        mockClient
      );

      expect(mockClient.connect).toHaveBeenCalledTimes(1);
      expect(mockClient.connect).toHaveBeenCalledWith(
        dummyUri,
        expect.objectContaining({
          serverSelectionTimeoutMS: 5000,
          connectTimeoutMS: 10000,
          socketTimeoutMS: 45000,
          maxPoolSize: 10,
          minPoolSize: 2,
        })
      );
      expect(conn.readyState).toBe(1);
      expect(isDatabaseConnected(mockClient)).toBe(true);
    });

    it("should map readyState numbers to readable status names", () => {
      expect(readyStateToName(0)).toBe("disconnected");
      expect(readyStateToName(1)).toBe("connected");
      expect(readyStateToName(2)).toBe("connecting");
      expect(readyStateToName(3)).toBe("disconnecting");
      expect(readyStateToName(99)).toBe("uninitialized");
    });
  });

  describe("2. Prevention of Duplicate Connections", () => {
    it("should return existing connection if readyState === 1 without calling connect()", async () => {
      const mockClient = createMockMongoose(1); // Already connected

      const conn = await connectToDatabase({ uri: dummyUri }, mockClient);

      expect(mockClient.connect).not.toHaveBeenCalled();
      expect(conn.readyState).toBe(1);
    });

    it("should reuse in-flight connection promise if already connecting", async () => {
      const mockClient = createMockMongoose(0);

      // Simulate a connection that takes 50ms
      (mockClient.connect as unknown as ReturnType<typeof vi.fn>).mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            (mockClient.connection as unknown as { readyState: number }).readyState = 2; // connecting
            setTimeout(() => {
              (mockClient.connection as unknown as { readyState: number }).readyState = 1;
              resolve(mockClient.connection);
            }, 50);
          })
      );

      // Start two concurrent calls
      const promise1 = connectToDatabase({ uri: dummyUri }, mockClient);
      const promise2 = connectToDatabase({ uri: dummyUri }, mockClient);

      const [conn1, conn2] = await Promise.all([promise1, promise2]);

      expect(mockClient.connect).toHaveBeenCalledTimes(1);
      expect(conn1).toBe(conn2);
    });
  });

  describe("3. Connection Failure & Credential Redaction", () => {
    it("should throw DatabaseConnectionError on connect failure", async () => {
      const mockClient = createMockMongoose(0);
      (mockClient.connect as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error("Server selection timed out after 5000 ms")
      );

      await expect(
        connectToDatabase({ uri: dummyUri }, mockClient)
      ).rejects.toThrow(DatabaseConnectionError);

      expect(isDatabaseConnected(mockClient)).toBe(false);
    });

    it("should never leak credentials in connection error messages", async () => {
      const secretPass = "TopSecretCredentials123";
      const uriWithPass = `mongodb+srv://admin:${secretPass}@cluster0.test.mongodb.net/testdb`;
      const mockClient = createMockMongoose(0);

      (mockClient.connect as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error(`Failed to connect to ${uriWithPass}: Authentication failed`)
      );

      try {
        await connectToDatabase({ uri: uriWithPass }, mockClient);
        expect.fail("Should have thrown DatabaseConnectionError");
      } catch (err: unknown) {
        expect(err).toBeInstanceOf(DatabaseConnectionError);
        const errMessage = String(err);
        expect(errMessage).not.toContain(secretPass);
      }
    });

    it("should reject when MONGODB_URI is not provided", async () => {
      const mockClient = createMockMongoose(0);
      delete process.env["MONGODB_URI"];

      await expect(
        connectToDatabase({ uri: "" }, mockClient)
      ).rejects.toThrow("MONGODB_URI is not configured");
    });
  });

  describe("4. Disconnect Behavior", () => {
    it("should call client.disconnect() when connected (readyState === 1)", async () => {
      const mockClient = createMockMongoose(1);

      await disconnectFromDatabase(mockClient);

      expect(mockClient.disconnect).toHaveBeenCalledTimes(1);
    });

    it("should resolve immediately when already disconnected (readyState === 0)", async () => {
      const mockClient = createMockMongoose(0);

      await disconnectFromDatabase(mockClient);

      expect(mockClient.disconnect).not.toHaveBeenCalled();
    });
  });

  describe("5. Readiness & State Queries", () => {
    it("isDatabaseConnected should return true only when readyState === 1", () => {
      expect(isDatabaseConnected(createMockMongoose(1))).toBe(true);
      expect(isDatabaseConnected(createMockMongoose(0))).toBe(false);
      expect(isDatabaseConnected(createMockMongoose(2))).toBe(false);
      expect(isDatabaseConnected(createMockMongoose(3))).toBe(false);
    });

    it("getConnectionState should return structured state information", () => {
      const client = createMockMongoose(1);
      const state = getConnectionState(client);

      expect(state).toEqual({
        readyState: 1,
        status: "connected",
        isConnected: true,
      });
    });
  });
});
