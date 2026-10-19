/**
 * Live MongoDB Atlas Integration Test.
 *
 * NOTE: This test is strictly separated from unit tests and will only run if a real,
 * active Atlas connection string is explicitly supplied via TEST_LIVE_ATLAS=true and MONGODB_URI.
 *
 * In standard CI or unit test environments, this test is safely marked as SKIPPED.
 */

import { describe, it, expect, afterAll } from "vitest";
import {
  connectToDatabase,
  disconnectFromDatabase,
  isDatabaseConnected,
} from "../../src/infrastructure/database/index.js";
import { isLiveIntegrationEnabled, getSafeTestDatabaseUri } from "./test-db.js";

const shouldRunLiveTest = isLiveIntegrationEnabled();

describe("Live MongoDB Atlas Integration (Optional)", () => {
  afterAll(async () => {
    if (shouldRunLiveTest) {
      await disconnectFromDatabase();
    }
  });

  const testFn = shouldRunLiveTest ? it : it.skip;

  testFn(
    "should establish a live TLS connection to MongoDB Atlas and perform a ping",
    async () => {
      const testUri = getSafeTestDatabaseUri();
      const conn = await connectToDatabase({
        uri: testUri ?? undefined,
        serverSelectionTimeoutMS: 5000,
      });

      expect(isDatabaseConnected()).toBe(true);
      expect(conn.readyState).toBe(1);

      // Verify actual database command ping
      if (conn.db) {
        const pingResult = await conn.db.admin().ping();
        expect(pingResult).toHaveProperty("ok", 1);
      }
    }
  );
});
