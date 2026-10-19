import { describe, it, expect } from "vitest";
import { validateTestDatabase } from "./integration/test-db.js";

describe("Test Database Safety Guardrails", () => {
  it("should accept valid dedicated test database 'component4_test'", () => {
    const res = validateTestDatabase(
      "mongodb+srv://user:pass@cluster0.test.mongodb.net/component4_test?retryWrites=true"
    );
    expect(res.isValid).toBe(true);
    expect(res.dbName).toBe("component4_test");
  });

  it("should accept databases ending in '_test'", () => {
    const res = validateTestDatabase(
      "mongodb://localhost:27017/event_service_test"
    );
    expect(res.isValid).toBe(true);
    expect(res.dbName).toBe("event_service_test");
  });

  it("should reject production/development database names", () => {
    const forbidden = [
      "event_intelligence",
      "admin",
      "local",
      "config",
      "production",
      "development",
      "dev",
    ];

    for (const name of forbidden) {
      const res = validateTestDatabase(
        `mongodb+srv://user:pass@cluster0.test.mongodb.net/${name}`
      );
      expect(res.isValid).toBe(false);
      expect(res.error).toContain("forbidden/production database name");
    }
  });

  it("should reject databases without explicit test suffix or name", () => {
    const res = validateTestDatabase(
      "mongodb+srv://user:pass@cluster0.test.mongodb.net/scheduled_events"
    );
    expect(res.isValid).toBe(false);
    expect(res.error).toContain("required test naming convention");
  });

  it("should reject URIs with missing database names", () => {
    const res = validateTestDatabase(
      "mongodb+srv://user:pass@cluster0.test.mongodb.net/?retryWrites=true"
    );
    expect(res.isValid).toBe(false);
    expect(res.error).toContain("Target database name is missing");
  });

  it("should reject malformed URIs", () => {
    const res = validateTestDatabase("not-a-valid-uri");
    expect(res.isValid).toBe(false);
    expect(res.error).toContain("Invalid connection URI syntax");
  });
});
