import { describe, it, expect, vi } from "vitest";
import request from "supertest";
import { app } from "../src/app.js";
import * as dbModule from "../src/infrastructure/database/index.js";

describe("Health & Readiness Endpoints", () => {
  describe("GET /api/health (Process Liveness Probe)", () => {
    it("should return 200 with status ok", async () => {
      const res = await request(app).get("/api/health");

      expect(res.status).toBe(200);
      expect(res.body).toMatchObject({
        status: "ok",
        component: "component-4-api",
        version: "0.1.0",
      });
      expect(res.body.timestamp).toBeDefined();
    });
  });

  describe("GET /api/health/ready (Service Readiness Probe)", () => {
    it("should return 503 with degraded status when database is disconnected", async () => {
      vi.spyOn(dbModule, "isDatabaseConnected").mockReturnValue(false);

      const res = await request(app).get("/api/health/ready");

      expect(res.status).toBe(503);
      expect(res.body).toMatchObject({
        status: "degraded",
        component: "component-4-api",
        database: "disconnected",
      });
      expect(res.body.timestamp).toBeDefined();
      // Ensure no raw internal connection details or credentials are leaked
      expect(JSON.stringify(res.body)).not.toContain("mongodb");
      expect(JSON.stringify(res.body)).not.toContain("password");
    });

    it("should return 200 with ok status when database is connected", async () => {
      vi.spyOn(dbModule, "isDatabaseConnected").mockReturnValue(true);

      const res = await request(app).get("/api/health/ready");

      expect(res.status).toBe(200);
      expect(res.body).toMatchObject({
        status: "ok",
        component: "component-4-api",
        database: "connected",
      });
      expect(res.body.timestamp).toBeDefined();
    });
  });
});
