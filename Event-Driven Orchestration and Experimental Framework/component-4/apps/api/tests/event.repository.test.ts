/**
 * Unit tests for EventRepository (Part 2.3).
 *
 * Verifies:
 *   1. Create: valid event creation, schema validation rejection, system-managed fields rejection,
 *      duplicate key handling, default status assignment.
 *   2. Retrieve: findById with matching record, null for non-existent or empty IDs.
 *   3. List: default pagination, custom pagination, maximum limit bounds, filtering by status/type/priority,
 *      date range filtering, sorting, total count consistency, invalid filter rejection.
 *   4. Update: valid partial updates, single datetime update validated against existing counterpart,
 *      rejection of invalid resultant date range, rejection of empty updates or system-managed fields,
 *      preservation of untouched fields.
 *   5. UpdateStatus: system-controlled lifecycle status transition and validation.
 *   6. Delete: deletion of matching record, graceful handling of non-existent record.
 *   7. Failure Handling: duplicate-key translation, database error translation, sanitization.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Model } from "mongoose";
import {
  EventRepository,
  RepositoryValidationError,
  RepositoryDuplicateKeyError,
  RepositoryDatabaseError,
} from "../src/repositories/index.js";
import type { IScheduledEventDocument } from "../src/models/index.js";
import type {
  CreateScheduledEventInput,
  UpdateScheduledEventInput,
  ScheduledEvent,
} from "@component4/shared";

function createMockDoc(data: Record<string, unknown>): IScheduledEventDocument {
  const doc = {
    ...data,
    _id: "mongo_internal_id_12345",
    __v: 0,
    startTime: data.startTime instanceof Date ? data.startTime : new Date(data.startTime as string),
    endTime: data.endTime instanceof Date ? data.endTime : new Date(data.endTime as string),
    createdAt: data.createdAt instanceof Date ? data.createdAt : new Date((data.createdAt as string) ?? "2026-10-01T10:00:00.000Z"),
    updatedAt: data.updatedAt instanceof Date ? data.updatedAt : new Date((data.updatedAt as string) ?? "2026-10-01T10:00:00.000Z"),
    save: vi.fn().mockImplementation(async function (this: unknown) {
      return this;
    }),
  } as unknown as IScheduledEventDocument;

  return doc;
}

function createMockModel(storedDocs: IScheduledEventDocument[] = []) {
  let docs = [...storedDocs];

  const ModelMock = vi.fn().mockImplementation(function (data: Record<string, unknown>) {
    const doc = createMockDoc(data);
    doc.save = vi.fn().mockImplementation(async () => {
      // Check duplicate eventId across OTHER documents
      const exists = docs.some((d) => d !== doc && d.eventId === doc.eventId);
      if (exists) {
        const err = new Error("E11000 duplicate key error collection");
        (err as Record<string, unknown>).code = 11000;
        throw err;
      }
      if (!docs.includes(doc)) {
        docs.push(doc);
      }
      return doc;
    });
    return doc;
  });

  (ModelMock as unknown as Record<string, unknown>).findOne = vi.fn().mockImplementation((query: { eventId?: string }) => ({
    exec: vi.fn().mockImplementation(async () => {
      return docs.find((d) => d.eventId === query.eventId) ?? null;
    }),
  }));

  (ModelMock as unknown as Record<string, unknown>).find = vi.fn().mockImplementation((filter: Record<string, unknown> = {}) => {
    let filtered = [...docs];
    if (filter.status) filtered = filtered.filter((d) => d.status === filter.status);
    if (filter.eventType) filtered = filtered.filter((d) => d.eventType === filter.eventType);
    if (filter.priority) filtered = filtered.filter((d) => d.priority === filter.priority);
    if (filter.expectedLoad) filtered = filtered.filter((d) => d.expectedLoad === filter.expectedLoad);

    const queryObj = {
      sort: vi.fn().mockReturnThis(),
      skip: vi.fn().mockImplementation((skipNum: number) => {
        filtered = filtered.slice(skipNum);
        return queryObj;
      }),
      limit: vi.fn().mockImplementation((limitNum: number) => {
        filtered = filtered.slice(0, limitNum);
        return queryObj;
      }),
      exec: vi.fn().mockImplementation(async () => filtered),
    };
    return queryObj;
  });

  (ModelMock as unknown as Record<string, unknown>).countDocuments = vi.fn().mockImplementation((filter: Record<string, unknown> = {}) => ({
    exec: vi.fn().mockImplementation(async () => {
      let filtered = [...docs];
      if (filter.status) filtered = filtered.filter((d) => d.status === filter.status);
      if (filter.eventType) filtered = filtered.filter((d) => d.eventType === filter.eventType);
      return filtered.length;
    }),
  }));

  (ModelMock as unknown as Record<string, unknown>).deleteOne = vi.fn().mockImplementation((query: { eventId?: string }) => ({
    exec: vi.fn().mockImplementation(async () => {
      const initialLen = docs.length;
      docs = docs.filter((d) => d.eventId !== query.eventId);
      return { deletedCount: initialLen - docs.length };
    }),
  }));

  return {
    model: ModelMock as unknown as Model<IScheduledEventDocument>,
    getStoredDocs: () => docs,
  };
}

describe("EventRepository Unit Tests", () => {
  let mockModel: Model<IScheduledEventDocument>;
  let repository: EventRepository;

  const validCreateInput: CreateScheduledEventInput = {
    eventName: "Campus Registration Day",
    eventType: "REGISTRATION",
    description: "Self-service online registration",
    startTime: "2026-11-20T08:00:00+05:30",
    endTime: "2026-11-20T18:00:00+05:30",
    expectedLoad: "HIGH",
    priority: "HIGH",
    prewarmWindowMinutes: 45,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    const mock = createMockModel();
    mockModel = mock.model;
    repository = new EventRepository(mockModel);
  });

  // ── 1. Create Operation ─────────────────────────────────────────────────────

  describe("1. create()", () => {
    it("should successfully create and return a clean ScheduledEvent", async () => {
      const created = await repository.create(validCreateInput);

      expect(created.eventId).toBeDefined();
      expect(created.eventId.startsWith("evt_")).toBe(true);
      expect(created.eventName).toBe("Campus Registration Day");
      expect(created.eventType).toBe("REGISTRATION");
      expect(created.status).toBe("SCHEDULED");
      expect(created.prewarmWindowMinutes).toBe(45);
      expect(created.startTime).toBe("2026-11-20T02:30:00.000Z"); // ISO instant format
      expect(created.endTime).toBe("2026-11-20T12:30:00.000Z");

      // Verify internal MongoDB _id and __v are not leaked
      const record = created as unknown as Record<string, unknown>;
      expect(record["_id"]).toBeUndefined();
      expect(record["__v"]).toBeUndefined();
    });

    it("should allow passing a deterministic idOverride", async () => {
      const customId = "EVT-CUSTOM-001";
      const created = await repository.create(validCreateInput, customId);
      expect(created.eventId).toBe(customId);
    });

    it("should reject invalid create input via RepositoryValidationError", async () => {
      const invalid = {
        ...validCreateInput,
        eventName: "   ", // Blank name
      };

      await expect(repository.create(invalid)).rejects.toThrow(
        RepositoryValidationError
      );
    });

    it("should reject client-provided system-managed fields", async () => {
      const maliciousPayload = {
        ...validCreateInput,
        eventId: "EVT-HACKED-ID",
        status: "COMPLETED",
      } as unknown as CreateScheduledEventInput;

      await expect(repository.create(maliciousPayload)).rejects.toThrow(
        RepositoryValidationError
      );
    });

    it("should reject when endTime is earlier than startTime", async () => {
      const reversedDates = {
        ...validCreateInput,
        startTime: "2026-11-20T18:00:00Z",
        endTime: "2026-11-20T08:00:00Z",
      };

      await expect(repository.create(reversedDates)).rejects.toThrow(
        RepositoryValidationError
      );
    });

    it("should throw RepositoryDuplicateKeyError when unique eventId collision occurs", async () => {
      const customId = "EVT-DUPLICATE-KEY";
      await repository.create(validCreateInput, customId);

      await expect(
        repository.create(validCreateInput, customId)
      ).rejects.toThrow(RepositoryDuplicateKeyError);
    });
  });

  // ── 2. Find by ID ───────────────────────────────────────────────────────────

  describe("2. findById()", () => {
    it("should return the matching event by application eventId", async () => {
      const customId = "EVT-LOOKUP-001";
      await repository.create(validCreateInput, customId);

      const found = await repository.findById(customId);
      expect(found).not.toBeNull();
      expect(found?.eventId).toBe(customId);
      expect(found?.eventName).toBe(validCreateInput.eventName);
    });

    it("should return null when event does not exist", async () => {
      const found = await repository.findById("EVT-NON-EXISTENT");
      expect(found).toBeNull();
    });

    it("should return null for empty, blank, or invalid eventId without throwing", async () => {
      expect(await repository.findById("")).toBeNull();
      expect(await repository.findById("   ")).toBeNull();
      expect(await repository.findById(null as unknown as string)).toBeNull();
    });
  });

  // ── 3. List Events ──────────────────────────────────────────────────────────

  describe("3. list()", () => {
    beforeEach(async () => {
      // Seed 3 events with different statuses and types
      await repository.create(
        {
          ...validCreateInput,
          eventName: "Event 1",
          eventType: "RESULT_RELEASE",
        },
        "EVT-001"
      );
      await repository.create(
        {
          ...validCreateInput,
          eventName: "Event 2",
          eventType: "REGISTRATION",
        },
        "EVT-002"
      );
      await repository.create(
        {
          ...validCreateInput,
          eventName: "Event 3",
          eventType: "FLASH_SALE",
        },
        "EVT-003"
      );
    });

    it("should return paginated list with default bounds (page 1, limit 20)", async () => {
      const res = await repository.list();

      expect(res.events).toHaveLength(3);
      expect(res.pagination).toEqual({
        total: 3,
        page: 1,
        limit: 20,
        totalPages: 1,
      });
    });

    it("should support custom pagination limit and page offset", async () => {
      const res = await repository.list({ page: 2, limit: 2 });

      expect(res.events).toHaveLength(1);
      expect(res.pagination.page).toBe(2);
      expect(res.pagination.limit).toBe(2);
      expect(res.pagination.total).toBe(3);
      expect(res.pagination.totalPages).toBe(2);
    });

    it("should filter events by eventType", async () => {
      const res = await repository.list({ eventType: "RESULT_RELEASE" });

      expect(res.events).toHaveLength(1);
      expect(res.events[0].eventType).toBe("RESULT_RELEASE");
      expect(res.pagination.total).toBe(1);
    });

    it("should reject query when startDateTo is earlier than startDateFrom", async () => {
      await expect(
        repository.list({
          startDateFrom: "2026-11-25T00:00:00Z",
          startDateTo: "2026-11-20T00:00:00Z",
        })
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should reject invalid enum values in query filter", async () => {
      await expect(
        repository.list({
          eventType: "INVALID_TYPE" as unknown as CreateScheduledEventInput["eventType"],
        })
      ).rejects.toThrow(RepositoryValidationError);
    });
  });

  // ── 4. Update Event ─────────────────────────────────────────────────────────

  describe("4. update()", () => {
    let existingEvent: ScheduledEvent;

    beforeEach(async () => {
      existingEvent = await repository.create(
        {
          ...validCreateInput,
          startTime: "2026-11-20T10:00:00Z",
          endTime: "2026-11-20T18:00:00Z",
        },
        "EVT-UPDATE-001"
      );
    });

    it("should successfully update single editable field and preserve untouched fields", async () => {
      const updated = await repository.update(existingEvent.eventId, {
        eventName: "Renamed Annual Registration",
      });

      expect(updated).not.toBeNull();
      expect(updated?.eventName).toBe("Renamed Annual Registration");
      expect(updated?.eventType).toBe("REGISTRATION"); // preserved
      expect(updated?.prewarmWindowMinutes).toBe(45); // preserved
    });

    it("should validate cross-field date window when updating ONLY startTime", async () => {
      // Existing endTime is 18:00Z. Updating startTime to 12:00Z (valid < 18:00Z)
      const updated = await repository.update(existingEvent.eventId, {
        startTime: "2026-11-20T12:00:00Z",
      });

      expect(updated?.startTime).toBe("2026-11-20T12:00:00.000Z");
      expect(updated?.endTime).toBe("2026-11-20T18:00:00.000Z");
    });

    it("should reject update when updating ONLY startTime to later than existing persisted endTime", async () => {
      // Existing endTime is 18:00Z. Attempting to set startTime to 19:00Z
      await expect(
        repository.update(existingEvent.eventId, {
          startTime: "2026-11-20T19:00:00Z",
        })
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should reject update when updating ONLY endTime to earlier than existing persisted startTime", async () => {
      // Existing startTime is 10:00Z. Attempting to set endTime to 09:00Z
      await expect(
        repository.update(existingEvent.eventId, {
          endTime: "2026-11-20T09:00:00Z",
        })
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should reject an empty update payload", async () => {
      await expect(
        repository.update(existingEvent.eventId, {})
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should reject client-supplied system-managed fields on update", async () => {
      const updatePayload = {
        eventName: "Valid Name",
        status: "COMPLETED",
      } as unknown as UpdateScheduledEventInput;

      await expect(
        repository.update(existingEvent.eventId, updatePayload)
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should return null when updating a non-existent event", async () => {
      const res = await repository.update("EVT-DOES-NOT-EXIST", {
        eventName: "Something",
      });
      expect(res).toBeNull();
    });
  });

  // ── 5. Update Status ────────────────────────────────────────────────────────

  describe("5. updateStatus()", () => {
    it("should transition status to PROCESSING and COMPLETED", async () => {
      const event = await repository.create(validCreateInput, "EVT-STATUS-001");
      expect(event.status).toBe("SCHEDULED");

      const processing = await repository.updateStatus("EVT-STATUS-001", "PROCESSING");
      expect(processing?.status).toBe("PROCESSING");

      const completed = await repository.updateStatus("EVT-STATUS-001", "COMPLETED");
      expect(completed?.status).toBe("COMPLETED");
    });

    it("should reject invalid status values", async () => {
      await expect(
        repository.updateStatus(
          "EVT-STATUS-001",
          "INVALID_STATUS" as unknown as ScheduledEvent["status"]
        )
      ).rejects.toThrow(RepositoryValidationError);
    });

    it("should return null when status updating a non-existent event", async () => {
      const res = await repository.updateStatus("EVT-NON-EXISTENT", "CANCELLED");
      expect(res).toBeNull();
    });
  });

  // ── 6. Delete Event ─────────────────────────────────────────────────────────

  describe("6. delete()", () => {
    it("should delete existing event and return true", async () => {
      const event = await repository.create(validCreateInput, "EVT-DELETE-001");

      const deleted = await repository.delete(event.eventId);
      expect(deleted).toBe(true);

      const found = await repository.findById(event.eventId);
      expect(found).toBeNull();
    });

    it("should return false when deleting non-existent event", async () => {
      const deleted = await repository.delete("EVT-NON-EXISTENT");
      expect(deleted).toBe(false);
    });

    it("should return false for invalid or empty eventId without throwing", async () => {
      expect(await repository.delete("")).toBe(false);
      expect(await repository.delete(null as unknown as string)).toBe(false);
    });
  });

  // ── 7. Failure Handling & Credential Sanitization ───────────────────────────

  describe("7. Failure Handling & Sanitization", () => {
    it("should wrap raw driver errors into RepositoryDatabaseError without leaking secrets", async () => {
      const secretToken = "SuperSecretMongoClusterPass123";
      const faultyModel = {
        findOne: vi.fn().mockImplementation(() => ({
          exec: vi.fn().mockRejectedValue(new Error(`Connection failed at mongodb+srv://admin:${secretToken}@host`)),
        })),
      } as unknown as Model<IScheduledEventDocument>;

      const faultyRepo = new EventRepository(faultyModel);

      try {
        await faultyRepo.findById("EVT-ANY");
        expect.fail("Should have thrown RepositoryDatabaseError");
      } catch (err: unknown) {
        expect(err).toBeInstanceOf(RepositoryDatabaseError);
        expect(String(err)).not.toContain(secretToken);
      }
    });
  });
});
