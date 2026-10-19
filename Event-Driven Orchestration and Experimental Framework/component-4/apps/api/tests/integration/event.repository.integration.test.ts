/**
// ─────────────────────────────────────────────────────────────────────────────
// Event Repository Live MongoDB Atlas Integration Tests (Part 2.4)
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Verifies real MongoDB persistence, unique index constraints, queries,
// bounded pagination, partial updates, and deletion against an isolated test database.
//
// Safety:
//   - Strict database name validation (MUST target 'component4_test' or '*_test').
//   - Safe skip when TEST_LIVE_ATLAS or MONGODB_TEST_URI is unconfigured.
//   - Zero credential or URI leakage.
// ─────────────────────────────────────────────────────────────────────────────
*/

import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import {
  EventRepository,
  RepositoryDuplicateKeyError,
  RepositoryValidationError,
} from "../../src/repositories/index.js";
import { ScheduledEventModel } from "../../src/models/index.js";
import type {
  CreateScheduledEventInput,
  ScheduledEvent,
} from "@component4/shared";
import {
  isLiveIntegrationEnabled,
  setupIntegrationDatabase,
  cleanTestDatabase,
  teardownIntegrationDatabase,
} from "./test-db.js";

const isEnabled = isLiveIntegrationEnabled();
const testSuite = isEnabled ? describe : describe.skip;

testSuite("EventRepository Live MongoDB Atlas Integration Tests", () => {
  let repository: EventRepository;

  beforeAll(async () => {
    if (isEnabled) {
      await setupIntegrationDatabase();
      repository = new EventRepository(ScheduledEventModel);
    }
  });

  afterAll(async () => {
    if (isEnabled) {
      await teardownIntegrationDatabase();
    }
  });

  beforeEach(async () => {
    if (isEnabled) {
      await cleanTestDatabase();
    }
  });

  const baseInput: CreateScheduledEventInput = {
    eventName: "Campus Registration Day",
    eventType: "REGISTRATION",
    description: "Self-service online course registration",
    startTime: "2026-11-20T08:00:00Z",
    endTime: "2026-11-20T18:00:00Z",
    expectedLoad: "HIGH",
    priority: "HIGH",
    prewarmWindowMinutes: 45,
  };

  // ── 6.1 Create & Persistence ───────────────────────────────────────────────

  describe("6.1 Create and Persistence", () => {
    it("should persist a valid event and return normalized ScheduledEvent", async () => {
      const created = await repository.create(baseInput);

      expect(created.eventId).toBeDefined();
      expect(created.eventId.startsWith("evt_")).toBe(true);
      expect(created.eventName).toBe("Campus Registration Day");
      expect(created.status).toBe("SCHEDULED");
      expect(created.createdAt).toBeDefined();
      expect(created.updatedAt).toBeDefined();

      // Verify date formats are ISO 8601 strings
      expect(new Date(created.startTime).toISOString()).toBe(created.startTime);
      expect(new Date(created.endTime).toISOString()).toBe(created.endTime);

      // Verify Mongoose internals are not leaked
      const raw = created as unknown as Record<string, unknown>;
      expect(raw["_id"]).toBeUndefined();
      expect(raw["__v"]).toBeUndefined();

      // Verify persistence directly in MongoDB Atlas
      const directDoc = await ScheduledEventModel.findOne({
        eventId: created.eventId,
      }).exec();
      expect(directDoc).not.toBeNull();
      expect(directDoc?.eventName).toBe(baseInput.eventName);
      expect(directDoc?.status).toBe("SCHEDULED");
    });

    it("should reject invalid payloads before persistence", async () => {
      const invalid = {
        ...baseInput,
        eventName: "   ",
      };

      await expect(repository.create(invalid)).rejects.toThrow(
        RepositoryValidationError
      );

      // Verify nothing was persisted
      const count = await ScheduledEventModel.countDocuments().exec();
      expect(count).toBe(0);
    });

    it("should enforce uniqueness on eventId via database unique index", async () => {
      const fixedId = "evt_it_unique_check_001";
      await repository.create(baseInput, fixedId);

      // Verify document exists
      const doc = await ScheduledEventModel.findOne({ eventId: fixedId }).exec();
      expect(doc).not.toBeNull();

      // Attempt inserting duplicate eventId
      await expect(
        repository.create(
          {
            ...baseInput,
            eventName: "Conflicting Event",
          },
          fixedId
        )
      ).rejects.toThrow(RepositoryDuplicateKeyError);
    });
  });

  // ── 6.2 Retrieve ───────────────────────────────────────────────────────────

  describe("6.2 Retrieve by ID", () => {
    it("should retrieve an existing event by application eventId", async () => {
      const created = await repository.create(baseInput, "evt_it_retrieve_001");
      const retrieved = await repository.findById("evt_it_retrieve_001");

      expect(retrieved).not.toBeNull();
      expect(retrieved?.eventId).toBe(created.eventId);
      expect(retrieved?.eventName).toBe(created.eventName);
    });

    it("should return null for non-existent eventId", async () => {
      const result = await repository.findById("evt_it_nonexistent");
      expect(result).toBeNull();
    });

    it("should not confuse MongoDB _id with application eventId", async () => {
      const created = await repository.create(baseInput, "evt_it_id_check_001");
      const directDoc = await ScheduledEventModel.findOne({
        eventId: created.eventId,
      }).exec();
      expect(directDoc).not.toBeNull();

      const mongoInternalId = String(directDoc?._id);
      // Querying by MongoDB _id using findById should safely return null
      const result = await repository.findById(mongoInternalId);
      expect(result).toBeNull();
    });
  });

  // ── 6.3 List, Filters, and Pagination ──────────────────────────────────────

  describe("6.3 List, Filters, and Pagination", () => {
    const fixtureEvents: Array<{
      id: string;
      name: string;
      type: CreateScheduledEventInput["eventType"];
      priority: CreateScheduledEventInput["priority"];
      status: "SCHEDULED" | "PROCESSING" | "COMPLETED";
      start: string;
      end: string;
    }> = [
      {
        id: "evt_it_list_001",
        name: "Midterm Exam Results",
        type: "RESULT_RELEASE",
        priority: "CRITICAL",
        status: "SCHEDULED",
        start: "2026-11-10T09:00:00Z",
        end: "2026-11-10T12:00:00Z",
      },
      {
        id: "evt_it_list_002",
        name: "Spring Registration",
        type: "REGISTRATION",
        priority: "HIGH",
        status: "PROCESSING",
        start: "2026-11-15T08:00:00Z",
        end: "2026-11-15T18:00:00Z",
      },
      {
        id: "evt_it_list_003",
        name: "Black Friday Sale",
        type: "FLASH_SALE",
        priority: "HIGH",
        status: "SCHEDULED",
        start: "2026-11-20T00:00:00Z",
        end: "2026-11-20T23:59:59Z",
      },
      {
        id: "evt_it_list_004",
        name: "Final Grade Publication",
        type: "RESULT_RELEASE",
        priority: "CRITICAL",
        status: "COMPLETED",
        start: "2026-11-25T10:00:00Z",
        end: "2026-11-25T16:00:00Z",
      },
      {
        id: "evt_it_list_005",
        name: "Late Add/Drop Window",
        type: "REGISTRATION",
        priority: "LOW",
        status: "SCHEDULED",
        start: "2026-11-30T08:00:00Z",
        end: "2026-11-30T17:00:00Z",
      },
    ];

    beforeEach(async () => {
      for (const item of fixtureEvents) {
        const created = await repository.create(
          {
            eventName: item.name,
            eventType: item.type,
            priority: item.priority,
            startTime: item.start,
            endTime: item.end,
            prewarmWindowMinutes: 30,
            expectedLoad: "MEDIUM",
          },
          item.id
        );

        if (item.status !== "SCHEDULED") {
          await repository.updateStatus(created.eventId, item.status);
        }
      }
    });

    it("should return default pagination (page 1, limit 20) with accurate total count", async () => {
      const res = await repository.list();

      expect(res.events).toHaveLength(5);
      expect(res.pagination).toEqual({
        total: 5,
        page: 1,
        limit: 20,
        totalPages: 1,
      });
    });

    it("should accurately paginate across records using custom page and limit", async () => {
      // Page 1: 2 events
      const page1 = await repository.list({ page: 1, limit: 2 });
      expect(page1.events).toHaveLength(2);
      expect(page1.pagination.total).toBe(5);
      expect(page1.pagination.totalPages).toBe(3);
      expect(page1.pagination.page).toBe(1);

      // Page 2: 2 events
      const page2 = await repository.list({ page: 2, limit: 2 });
      expect(page2.events).toHaveLength(2);
      expect(page2.pagination.page).toBe(2);

      // Page 3: 1 event
      const page3 = await repository.list({ page: 3, limit: 2 });
      expect(page3.events).toHaveLength(1);
      expect(page3.pagination.page).toBe(3);

      // Assert page 1 and page 2 have completely disjoint event IDs
      const ids1 = page1.events.map((e) => e.eventId);
      const ids2 = page2.events.map((e) => e.eventId);
      expect(ids1.some((id) => ids2.includes(id))).toBe(false);
    });

    it("should filter by status", async () => {
      const res = await repository.list({ status: "SCHEDULED" });
      expect(res.events).toHaveLength(3);
      expect(res.pagination.total).toBe(3);
      res.events.forEach((e) => expect(e.status).toBe("SCHEDULED"));
    });

    it("should filter by eventType", async () => {
      const res = await repository.list({ eventType: "RESULT_RELEASE" });
      expect(res.events).toHaveLength(2);
      expect(res.pagination.total).toBe(2);
      res.events.forEach((e) => expect(e.eventType).toBe("RESULT_RELEASE"));
    });

    it("should filter by priority", async () => {
      const res = await repository.list({ priority: "CRITICAL" });
      expect(res.events).toHaveLength(2);
      expect(res.pagination.total).toBe(2);
      res.events.forEach((e) => expect(e.priority).toBe("CRITICAL"));
    });

    it("should filter by date range (startDateFrom & startDateTo)", async () => {
      const res = await repository.list({
        startDateFrom: "2026-11-12T00:00:00Z",
        startDateTo: "2026-11-22T00:00:00Z",
      });

      // Events on Nov 15 and Nov 20
      expect(res.events).toHaveLength(2);
      expect(res.pagination.total).toBe(2);
      expect(res.events.map((e) => e.eventId)).toEqual([
        "evt_it_list_002",
        "evt_it_list_003",
      ]);
    });

    it("should apply deterministic sorting (asc by startTime with tie-breaker)", async () => {
      const res = await repository.list({ sortBy: "startTime", sortOrder: "asc" });
      const dates = res.events.map((e) => new Date(e.startTime).getTime());

      for (let i = 0; i < dates.length - 1; i++) {
        expect(dates[i]).toBeLessThanOrEqual(dates[i + 1]);
      }
    });

    it("should reject invalid date range where startDateTo < startDateFrom", async () => {
      await expect(
        repository.list({
          startDateFrom: "2026-11-25T00:00:00Z",
          startDateTo: "2026-11-10T00:00:00Z",
        })
      ).rejects.toThrow(RepositoryValidationError);
    });
  });

  // ── 6.4 Update ─────────────────────────────────────────────────────────────

  describe("6.4 Update Event", () => {
    let targetEvent: ScheduledEvent;

    beforeEach(async () => {
      targetEvent = await repository.create(
        {
          ...baseInput,
          eventName: "Original Event Name",
          startTime: "2026-11-20T10:00:00Z",
          endTime: "2026-11-20T18:00:00Z",
        },
        "evt_it_update_001"
      );
    });

    it("should persist a valid partial update and update updatedAt timestamp", async () => {
      // Small pause to guarantee timestamp distinction
      await new Promise((r) => setTimeout(r, 50));

      const updated = await repository.update(targetEvent.eventId, {
        eventName: "Updated Event Name",
        description: "New updated description",
      });

      expect(updated).not.toBeNull();
      expect(updated?.eventName).toBe("Updated Event Name");
      expect(updated?.description).toBe("New updated description");
      expect(updated?.eventType).toBe(targetEvent.eventType); // preserved

      expect(new Date(updated!.updatedAt).getTime()).toBeGreaterThanOrEqual(
        new Date(targetEvent.updatedAt).getTime()
      );

      // Verify in MongoDB Atlas
      const directDoc = await ScheduledEventModel.findOne({
        eventId: targetEvent.eventId,
      }).exec();
      expect(directDoc?.eventName).toBe("Updated Event Name");
    });

    it("should validate cross-field date window when updating ONLY startTime against persisted endTime", async () => {
      // Existing endTime is 18:00Z. Updating startTime to 14:00Z (valid < 18:00Z)
      const validUpdate = await repository.update(targetEvent.eventId, {
        startTime: "2026-11-20T14:00:00Z",
      });
      expect(validUpdate?.startTime).toBe("2026-11-20T14:00:00.000Z");
      expect(validUpdate?.endTime).toBe("2026-11-20T18:00:00.000Z");

      // Updating startTime to 19:00Z (invalid > 18:00Z persisted endTime)
      await expect(
        repository.update(targetEvent.eventId, {
          startTime: "2026-11-20T19:00:00Z",
        })
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should validate cross-field date window when updating ONLY endTime against persisted startTime", async () => {
      // Existing startTime is 10:00Z. Attempting to set endTime to 08:00Z
      await expect(
        repository.update(targetEvent.eventId, {
          endTime: "2026-11-20T08:00:00Z",
        })
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should reject empty update payloads", async () => {
      await expect(
        repository.update(targetEvent.eventId, {})
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should reject modification of system-managed fields via update()", async () => {
      const malicious = {
        eventName: "Legit Name",
        status: "COMPLETED",
      } as unknown as Record<string, unknown>;

      await expect(
        repository.update(targetEvent.eventId, malicious)
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should return null when updating a non-existent event", async () => {
      const result = await repository.update("evt_it_ghost", {
        eventName: "Ghost Event",
      });
      expect(result).toBeNull();
    });
  });

  // ── 6.5 Delete ─────────────────────────────────────────────────────────────

  describe("6.5 Delete Event", () => {
    it("should delete existing event from database and leave unrelated records intact", async () => {
      const eventA = await repository.create(baseInput, "evt_it_del_A");
      const eventB = await repository.create(baseInput, "evt_it_del_B");

      const deleted = await repository.delete("evt_it_del_A");
      expect(deleted).toBe(true);

      // Event A should no longer be found
      expect(await repository.findById("evt_it_del_A")).toBeNull();
      const docA = await ScheduledEventModel.findOne({ eventId: "evt_it_del_A" }).exec();
      expect(docA).toBeNull();

      // Event B must remain intact
      const foundB = await repository.findById("evt_it_del_B");
      expect(foundB).not.toBeNull();
      expect(foundB?.eventId).toBe(eventB.eventId);
    });

    it("should return false when deleting non-existent event", async () => {
      const result = await repository.delete("evt_it_does_not_exist");
      expect(result).toBe(false);
    });
  });
});
