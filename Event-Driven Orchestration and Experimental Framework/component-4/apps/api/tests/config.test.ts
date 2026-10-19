/**
 * Unit tests for API Environment Configuration & Validation.
 *
 * Verifies:
 *   1. Validation of required MONGODB_URI.
 *   2. Detection of invalid or malformed URI schemes.
 *   3. Safe credential redaction via sanitizeMongoUri.
 *   4. Default fallbacks for ports, hosts, timeouts, and pools.
 *   5. Total absence of leaked passwords in ConfigValidationError.
 */

import { describe, it, expect } from "vitest";
import {
  parseEnvironmentConfig,
  sanitizeMongoUri,
  ConfigValidationError,
} from "../src/config/index.js";

describe("Environment Configuration & Validation", () => {
  const validAtlasUri =
    "mongodb+srv://admin_user:SuperSecretPassword123@cluster0.abcde.mongodb.net/event_intelligence?retryWrites=true&w=majority";
  const validStandardUri =
    "mongodb://dbuser:Pass456@localhost:27017/event_intelligence?authSource=admin";

  describe("1. Valid Configuration", () => {
    it("should parse valid Atlas URI with standard defaults", () => {
      const config = parseEnvironmentConfig({
        MONGODB_URI: validAtlasUri,
      });

      expect(config.MONGODB_URI).toBe(validAtlasUri);
      expect(config.NODE_ENV).toBe("development");
      expect(config.API_PORT).toBe(4004);
      expect(config.API_HOST).toBe("0.0.0.0");
      expect(config.DB_SERVER_SELECTION_TIMEOUT_MS).toBe(5000);
      expect(config.DB_CONNECT_TIMEOUT_MS).toBe(10000);
      expect(config.DB_MAX_POOL_SIZE).toBe(10);
      expect(config.DB_MIN_POOL_SIZE).toBe(2);
    });

    it("should accept valid standard mongodb:// scheme", () => {
      const config = parseEnvironmentConfig({
        MONGODB_URI: validStandardUri,
      });
      expect(config.MONGODB_URI).toBe(validStandardUri);
    });

    it("should allow custom ports, hosts, and timeout overrides", () => {
      const config = parseEnvironmentConfig({
        MONGODB_URI: validAtlasUri,
        API_PORT: "5050",
        API_HOST: "127.0.0.1",
        NODE_ENV: "production",
        DB_SERVER_SELECTION_TIMEOUT_MS: "3000",
        DB_CONNECT_TIMEOUT_MS: "8000",
        DB_MAX_POOL_SIZE: "25",
        DB_MIN_POOL_SIZE: "5",
      });

      expect(config.API_PORT).toBe(5050);
      expect(config.API_HOST).toBe("127.0.0.1");
      expect(config.NODE_ENV).toBe("production");
      expect(config.DB_SERVER_SELECTION_TIMEOUT_MS).toBe(3000);
      expect(config.DB_CONNECT_TIMEOUT_MS).toBe(8000);
      expect(config.DB_MAX_POOL_SIZE).toBe(25);
      expect(config.DB_MIN_POOL_SIZE).toBe(5);
    });

    it("should allow omitting MONGODB_URI when requireDb is false", () => {
      const config = parseEnvironmentConfig({}, { requireDb: false });
      expect(config.MONGODB_URI).toBeUndefined();
      expect(config.API_PORT).toBe(4004);
    });
  });

  describe("2. Missing and Malformed Configuration", () => {
    it("should throw ConfigValidationError when MONGODB_URI is missing", () => {
      expect(() => parseEnvironmentConfig({})).toThrow(ConfigValidationError);
    });

    it("should throw ConfigValidationError when MONGODB_URI is empty or whitespace", () => {
      expect(() => parseEnvironmentConfig({ MONGODB_URI: "" })).toThrow(
        ConfigValidationError
      );
      expect(() => parseEnvironmentConfig({ MONGODB_URI: "   " })).toThrow(
        ConfigValidationError
      );
    });

    it("should reject URIs with invalid protocol schemes (e.g. http, postgres, redis)", () => {
      expect(() =>
        parseEnvironmentConfig({
          MONGODB_URI: "http://localhost:27017/db",
        })
      ).toThrow(ConfigValidationError);

      expect(() =>
        parseEnvironmentConfig({
          MONGODB_URI: "postgresql://user:pass@localhost:5432/db",
        })
      ).toThrow(ConfigValidationError);

      expect(() =>
        parseEnvironmentConfig({
          MONGODB_URI: "redis://localhost:6379",
        })
      ).toThrow(ConfigValidationError);
    });

    it("should reject negative or non-integer API_PORT", () => {
      expect(() =>
        parseEnvironmentConfig({
          MONGODB_URI: validAtlasUri,
          API_PORT: "-1",
        })
      ).toThrow(ConfigValidationError);

      expect(() =>
        parseEnvironmentConfig({
          MONGODB_URI: validAtlasUri,
          API_PORT: "not-a-number",
        })
      ).toThrow(ConfigValidationError);
    });
  });

  describe("3. Security & Credential Redaction", () => {
    it("sanitizeMongoUri should redact passwords from Atlas mongodb+srv URIs", () => {
      const sanitized = sanitizeMongoUri(validAtlasUri);
      expect(sanitized).not.toContain("SuperSecretPassword123");
      expect(sanitized).toContain("admin_user:****@cluster0.abcde.mongodb.net");
    });

    it("sanitizeMongoUri should redact passwords from standard mongodb URIs", () => {
      const sanitized = sanitizeMongoUri(validStandardUri);
      expect(sanitized).not.toContain("Pass456");
      expect(sanitized).toContain("dbuser:****@localhost:27017");
    });

    it("sanitizeMongoUri should handle empty or undefined inputs safely", () => {
      expect(sanitizeMongoUri("")).toBe("[UNDEFINED_OR_EMPTY_URI]");
      expect(sanitizeMongoUri(undefined)).toBe("[UNDEFINED_OR_EMPTY_URI]");
    });

    it("validation error messages should never print secret credentials", () => {
      const maliciousPass = "SuperConfidentialToken12345";
      try {
        parseEnvironmentConfig({
          MONGODB_URI: `invalid-scheme://user:${maliciousPass}@host/db`,
        });
        expect.fail("Should have thrown ConfigValidationError");
      } catch (err: unknown) {
        expect(err).toBeInstanceOf(ConfigValidationError);
        const errorString = String(err);
        expect(errorString).not.toContain(maliciousPass);
      }
    });
  });
});
