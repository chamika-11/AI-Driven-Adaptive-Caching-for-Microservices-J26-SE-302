// ─────────────────────────────────────────────────────────────────────────────
// Event Repository — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Encapsulates all database persistence operations for scheduled events.
//
// Responsibilities:
//   1. Validates inputs using existing shared Zod schemas before persistence.
//   2. Generates application-level event IDs (crypto.randomUUID).
//   3. Strictly isolates internal MongoDB details (_id, __v) from API contracts.
//   4. Enforces cross-field temporal consistency on partial updates against existing state.
//   5. Maps query filters safely to avoid arbitrary MongoDB query injection.
//   6. Translates driver exceptions into typed, sanitized RepositoryError subclasses.
// ─────────────────────────────────────────────────────────────────────────────

import crypto from "node:crypto";
import type { Model, FilterQuery } from "mongoose";
import {
  CreateScheduledEventInputSchema,
  UpdateScheduledEventInputSchema,
  EventStatusSchema,
  ListEventsQuerySchema,
  type ScheduledEvent,
  type CreateScheduledEventInput,
  type UpdateScheduledEventInput,
  type EventStatus,
  type EventListResponse,
  type ListEventsQuery,
} from "@component4/shared";
import {
  ScheduledEventModel,
  mapDocumentToScheduledEvent,
  type IScheduledEventDocument,
} from "../models/index.js";
import {
  RepositoryError,
  RepositoryValidationError,
  RepositoryDuplicateKeyError,
  RepositoryDatabaseError,
} from "./errors.js";

export interface IEventRepository {
  create(input: CreateScheduledEventInput, idOverride?: string): Promise<ScheduledEvent>;
  findById(eventId: string): Promise<ScheduledEvent | null>;
  list(query?: ListEventsQuery): Promise<EventListResponse>;
  update(eventId: string, input: UpdateScheduledEventInput): Promise<ScheduledEvent | null>;
  updateStatus(eventId: string, newStatus: EventStatus): Promise<ScheduledEvent | null>;
  delete(eventId: string): Promise<boolean>;
}

export class EventRepository implements IEventRepository {
  private readonly model: Model<IScheduledEventDocument>;

  /**
   * Initializes the repository with Mongoose model dependency injection.
   * Defaults to the canonical ScheduledEventModel.
   */
  constructor(model: Model<IScheduledEventDocument> = ScheduledEventModel) {
    this.model = model;
  }

  /**
   * 4.1 Create Event
   * Validates client input, assigns unique eventId, and stores document with SCHEDULED status.
   */
  public async create(
    input: CreateScheduledEventInput,
    idOverride?: string
  ): Promise<ScheduledEvent> {
    // Step 1: Pre-persistence validation using shared Zod contract
    const validationResult = CreateScheduledEventInputSchema.safeParse(input);
    if (!validationResult.success) {
      const issueMessages = validationResult.error.issues.map(
        (issue) => `${issue.path.join(".")}: ${issue.message}`
      );
      throw new RepositoryValidationError(
        `Event creation validation failed: ${issueMessages.join("; ")}`,
        issueMessages
      );
    }

    const validated = validationResult.data;
    const eventId = idOverride ?? `evt_${crypto.randomUUID()}`;

    // Step 2: Instantiate Mongoose document
    const doc = new this.model({
      eventId,
      eventName: validated.eventName,
      eventType: validated.eventType,
      description: validated.description,
      startTime: new Date(validated.startTime),
      endTime: new Date(validated.endTime),
      expectedLoad: validated.expectedLoad,
      priority: validated.priority,
      prewarmWindowMinutes: validated.prewarmWindowMinutes,
      status: "SCHEDULED",
    });

    // Step 3: Persist to MongoDB Atlas
    try {
      const savedDoc = await doc.save();
      return mapDocumentToScheduledEvent(savedDoc);
    } catch (error: unknown) {
      this.handleMongooseError(error, eventId);
    }
  }

  /**
   * 4.2 Find Event by ID
   * Retrieves a single event by application-level eventId. Returns null if missing.
   */
  public async findById(eventId: string): Promise<ScheduledEvent | null> {
    if (!eventId || typeof eventId !== "string" || eventId.trim() === "") {
      return null;
    }

    try {
      const doc = await this.model.findOne({ eventId: eventId.trim() }).exec();
      if (!doc) {
        return null;
      }
      return mapDocumentToScheduledEvent(doc);
    } catch (error: unknown) {
      this.handleMongooseError(error, eventId);
    }
  }

  /**
   * 4.3 List Events
   * Supports structured filtering, bounded pagination, deterministic sorting,
   * and accurate total-count metadata.
   */
  public async list(query: ListEventsQuery = {}): Promise<EventListResponse> {
    // Step 1: Validate query parameters and date ranges
    const queryValidation = ListEventsQuerySchema.safeParse(query);
    if (!queryValidation.success) {
      const issueMessages = queryValidation.error.issues.map(
        (issue) => `${issue.path.join(".")}: ${issue.message}`
      );
      throw new RepositoryValidationError(
        `Invalid event list query: ${issueMessages.join("; ")}`,
        issueMessages
      );
    }

    const validated = queryValidation.data;
    const page = validated.page ?? 1;
    const limit = validated.limit ?? 20;
    const sortBy = validated.sortBy ?? "startTime";
    const sortOrder = validated.sortOrder === "desc" ? -1 : 1;

    // Step 2: Build sanitized MongoDB filter (prevents arbitrary operator injection)
    const filter: FilterQuery<IScheduledEventDocument> = {};

    if (validated.status) {
      filter.status = validated.status;
    }
    if (validated.eventType) {
      filter.eventType = validated.eventType;
    }
    if (validated.priority) {
      filter.priority = validated.priority;
    }
    if (validated.expectedLoad) {
      filter.expectedLoad = validated.expectedLoad;
    }

    if (validated.startDateFrom || validated.startDateTo) {
      filter.startTime = {};
      if (validated.startDateFrom) {
        filter.startTime.$gte = new Date(validated.startDateFrom);
      }
      if (validated.startDateTo) {
        filter.startTime.$lte = new Date(validated.startDateTo);
      }
    }

    const skip = (page - 1) * limit;
    const sortOptions: Record<string, 1 | -1> = {
      [sortBy]: sortOrder,
      eventId: 1, // Deterministic tie-breaker
    };

    // Step 3: Query documents and count in parallel
    try {
      const [docs, total] = await Promise.all([
        this.model
          .find(filter)
          .sort(sortOptions)
          .skip(skip)
          .limit(limit)
          .exec(),
        this.model.countDocuments(filter).exec(),
      ]);

      const totalPages = total === 0 ? 0 : Math.ceil(total / limit);

      return {
        events: docs.map(mapDocumentToScheduledEvent),
        pagination: {
          total,
          page,
          limit,
          totalPages,
        },
      };
    } catch (error: unknown) {
      this.handleMongooseError(error);
    }
  }

  /**
   * 4.4 Update Event
   * Validates partial update input, verifies resulting date invariants (endTime > startTime)
   * against the persisted state, and updates the event.
   */
  public async update(
    eventId: string,
    input: UpdateScheduledEventInput
  ): Promise<ScheduledEvent | null> {
    if (!eventId || typeof eventId !== "string" || eventId.trim() === "") {
      return null;
    }

    // Step 1: Validate input against UpdateScheduledEventInputSchema
    const validationResult = UpdateScheduledEventInputSchema.safeParse(input);
    if (!validationResult.success) {
      const issueMessages = validationResult.error.issues.map(
        (issue) => `${issue.path.join(".")}: ${issue.message}`
      );
      throw new RepositoryValidationError(
        `Event update validation failed: ${issueMessages.join("; ")}`,
        issueMessages
      );
    }

    const validated = validationResult.data;

    try {
      // Step 2: Fetch existing document
      const doc = await this.model.findOne({ eventId: eventId.trim() }).exec();
      if (!doc) {
        return null;
      }

      // Step 3: Apply partial updates
      if (validated.eventName !== undefined) {
        doc.eventName = validated.eventName;
      }
      if (validated.eventType !== undefined) {
        doc.eventType = validated.eventType;
      }
      if (validated.description !== undefined) {
        doc.description = validated.description;
      }
      if (validated.startTime !== undefined) {
        doc.startTime = new Date(validated.startTime);
      }
      if (validated.endTime !== undefined) {
        doc.endTime = new Date(validated.endTime);
      }
      if (validated.expectedLoad !== undefined) {
        doc.expectedLoad = validated.expectedLoad;
      }
      if (validated.priority !== undefined) {
        doc.priority = validated.priority;
      }
      if (validated.prewarmWindowMinutes !== undefined) {
        doc.prewarmWindowMinutes = validated.prewarmWindowMinutes;
      }

      // Step 4: Validate cross-field temporal constraint against merged state
      // (Handles case where only startTime or only endTime was updated)
      if (doc.endTime.getTime() <= doc.startTime.getTime()) {
        throw new RepositoryValidationError(
          "Update resulted in an invalid event window: endTime must be strictly later than startTime",
          ["endTime: endTime must be strictly later than startTime"]
        );
      }

      // Step 5: Save and return mapped result
      const savedDoc = await doc.save();
      return mapDocumentToScheduledEvent(savedDoc);
    } catch (error: unknown) {
      this.handleMongooseError(error, eventId);
    }
  }

  /**
   * 4.5 Update Lifecycle Status
   * System-controlled status transition method.
   */
  public async updateStatus(
    eventId: string,
    newStatus: EventStatus
  ): Promise<ScheduledEvent | null> {
    if (!eventId || typeof eventId !== "string" || eventId.trim() === "") {
      return null;
    }

    const statusValidation = EventStatusSchema.safeParse(newStatus);
    if (!statusValidation.success) {
      throw new RepositoryValidationError(
        `Invalid status '${newStatus}'. Must be one of: SCHEDULED, PROCESSING, COMPLETED, CANCELLED.`,
        statusValidation.error.issues.map((i) => i.message)
      );
    }

    try {
      const doc = await this.model.findOne({ eventId: eventId.trim() }).exec();
      if (!doc) {
        return null;
      }

      doc.status = statusValidation.data;
      const savedDoc = await doc.save();
      return mapDocumentToScheduledEvent(savedDoc);
    } catch (error: unknown) {
      this.handleMongooseError(error, eventId);
    }
  }

  /**
   * 4.6 Delete Event
   * Deletes the scheduled event matching application-level eventId.
   */
  public async delete(eventId: string): Promise<boolean> {
    if (!eventId || typeof eventId !== "string" || eventId.trim() === "") {
      return false;
    }

    try {
      const result = await this.model.deleteOne({ eventId: eventId.trim() }).exec();
      return (result.deletedCount ?? 0) > 0;
    } catch (error: unknown) {
      this.handleMongooseError(error, eventId);
    }
  }

  /**
   * Translates underlying driver and database errors into typed, sanitized RepositoryErrors.
   */
  private handleMongooseError(error: unknown, eventId?: string): never {
    if (error instanceof RepositoryError) {
      throw error;
    }

    if (error && typeof error === "object") {
      const err = error as Record<string, unknown>;

      // Duplicate key error on unique index (e.g. eventId)
      if (err.code === 11000) {
        throw new RepositoryDuplicateKeyError("eventId", eventId ?? "unknown");
      }

      // Mongoose Schema ValidationError
      if (err.name === "ValidationError") {
        const issues = Object.values(
          (err.errors as Record<string, { message: string }>) || {}
        ).map((e) => e.message);
        throw new RepositoryValidationError(
          "Document persistence validation failed",
          issues
        );
      }
    }

    const msg = error instanceof Error ? error.message : String(error);
    throw new RepositoryDatabaseError(msg);
  }
}
