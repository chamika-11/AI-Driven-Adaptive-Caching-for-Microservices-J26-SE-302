// ─────────────────────────────────────────────────────────────────────────────
// Scheduled Event Mongoose Model — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Defines the MongoDB Atlas persistence schema, indexes, document interface,
// and contract conversion boundary for scheduled business events.
//
// Key Architectural Design Decisions:
//   1. Application vs Database ID: `eventId` is the primary business identifier
//      (indexed unique); MongoDB's internal `_id` is retained for database-level
//      operations but excluded from domain API output.
//   2. Temporal Semantics: `startTime`, `endTime`, `createdAt`, and `updatedAt`
//      are stored as BSON Dates (instants in time) in MongoDB Atlas for query
//      efficiency, but serialized to ISO 8601 strings when conforming to the
//      shared API contract (`ScheduledEvent`).
//   3. Lifecycle & Query Indexes: Compound index on `{ status: 1, startTime: 1 }`
//      enables the future Event Scheduler and monitoring workers to query active
//      events chronologically with zero in-memory sort overhead.
//   4. Reload-Safe: Guards against Mongoose `OverwriteModelError` during `tsx watch`
//      hot reloads without initiating connection side effects.
// ─────────────────────────────────────────────────────────────────────────────

import mongoose, { Schema, model, type Document, type Model } from "mongoose";
import {
  EVENT_TYPES,
  EXPECTED_LOADS,
  EVENT_PRIORITIES,
  EVENT_STATUSES,
  EVENT_NAME_MIN_LENGTH,
  EVENT_NAME_MAX_LENGTH,
  DESCRIPTION_MAX_LENGTH,
  PREWARM_WINDOW_MIN_MINUTES,
  PREWARM_WINDOW_MAX_MINUTES,
  type EventType,
  type ExpectedLoad,
  type EventPriority,
  type EventStatus,
  type ScheduledEvent,
} from "@component4/shared";

/**
 * TypeScript interface representing the stored MongoDB document data.
 */
export interface IScheduledEvent {
  eventId: string;
  eventName: string;
  eventType: EventType;
  description?: string;
  startTime: Date;
  endTime: Date;
  expectedLoad?: ExpectedLoad;
  priority?: EventPriority;
  prewarmWindowMinutes: number;
  status: EventStatus;
  createdAt: Date;
  updatedAt: Date;
}

/**
 * Document interface including Mongoose document methods.
 */
export interface IScheduledEventDocument extends IScheduledEvent, Document {
  toScheduledEvent(): ScheduledEvent;
}

/**
 * Mongoose Schema definition for Scheduled Events.
 */
export const scheduledEventSchema = new Schema<IScheduledEventDocument>(
  {
    eventId: {
      type: String,
      required: [true, "eventId is required"],
      unique: true,
      trim: true,
      minlength: [1, "eventId cannot be empty"],
    },

    eventName: {
      type: String,
      required: [true, "eventName is required"],
      trim: true,
      minlength: [EVENT_NAME_MIN_LENGTH, "eventName cannot be empty"],
      maxlength: [
        EVENT_NAME_MAX_LENGTH,
        `eventName cannot exceed ${EVENT_NAME_MAX_LENGTH} characters`,
      ],
    },

    eventType: {
      type: String,
      required: [true, "eventType is required"],
      enum: {
        values: EVENT_TYPES,
        message: "Invalid eventType `{VALUE}`. Must be a valid shared EventType.",
      },
    },

    description: {
      type: String,
      trim: true,
      maxlength: [
        DESCRIPTION_MAX_LENGTH,
        `description cannot exceed ${DESCRIPTION_MAX_LENGTH} characters`,
      ],
    },

    startTime: {
      type: Date,
      required: [true, "startTime is required"],
    },

    endTime: {
      type: Date,
      required: [true, "endTime is required"],
      validate: {
        validator: function (
          this: IScheduledEventDocument | (Document & { startTime?: Date }),
          val: Date
        ): boolean {
          const start = this.startTime;
          if (!start || !val) {
            return true; // Let required validator handle missing dates
          }
          return val.getTime() > start.getTime();
        },
        message: "endTime must be strictly later than startTime",
      },
    },

    expectedLoad: {
      type: String,
      enum: {
        values: EXPECTED_LOADS,
        message: "Invalid expectedLoad `{VALUE}`. Must be a valid shared ExpectedLoad.",
      },
    },

    priority: {
      type: String,
      enum: {
        values: EVENT_PRIORITIES,
        message: "Invalid priority `{VALUE}`. Must be a valid shared EventPriority.",
      },
    },

    prewarmWindowMinutes: {
      type: Number,
      required: [true, "prewarmWindowMinutes is required"],
      validate: {
        validator: function (val: number): boolean {
          return (
            Number.isInteger(val) &&
            val >= PREWARM_WINDOW_MIN_MINUTES &&
            val <= PREWARM_WINDOW_MAX_MINUTES
          );
        },
        message: `prewarmWindowMinutes must be an integer between ${PREWARM_WINDOW_MIN_MINUTES} and ${PREWARM_WINDOW_MAX_MINUTES}`,
      },
    },

    status: {
      type: String,
      required: [true, "status is required"],
      enum: {
        values: EVENT_STATUSES,
        message: "Invalid status `{VALUE}`. Must be a valid shared EventStatus.",
      },
      default: "SCHEDULED",
    },
  },
  {
    timestamps: true, // Automatically manages createdAt and updatedAt as BSON Dates
    strict: true,     // Rejects un-declared fields from persistence
    collection: "scheduled_events",
  }
);

// ── Indexes ──────────────────────────────────────────────────────────────────
// Note: eventId uniqueness is declared inline on the field (`unique: true`).
//
// Compound index for event querying and scheduling triggers:
// Query Pattern: Finding events by lifecycle state (e.g. status: "SCHEDULED" or "PROCESSING")
// ordered chronologically by startTime for prewarm window detection and event pipeline execution.
scheduledEventSchema.index({ status: 1, startTime: 1 });

// ── Contract Mapping Boundary ────────────────────────────────────────────────

/**
 * Maps a Mongoose document or database record to the shared ScheduledEvent contract.
 *
 * Enforces:
 *   - BSON Date conversion to ISO 8601 strings.
 *   - Exclusion of internal `_id` and `__v` properties from the API contract.
 *   - Preservation of `eventId` as the application-level domain identifier.
 */
export function mapDocumentToScheduledEvent(
  doc: Partial<IScheduledEvent> & { _id?: unknown; __v?: unknown }
): ScheduledEvent {
  const event: ScheduledEvent = {
    eventId: doc.eventId!,
    eventName: doc.eventName!,
    eventType: doc.eventType!,
    startTime:
      doc.startTime instanceof Date
        ? doc.startTime.toISOString()
        : String(doc.startTime),
    endTime:
      doc.endTime instanceof Date
        ? doc.endTime.toISOString()
        : String(doc.endTime),
    prewarmWindowMinutes: doc.prewarmWindowMinutes!,
    status: doc.status!,
    createdAt:
      doc.createdAt instanceof Date
        ? doc.createdAt.toISOString()
        : String(doc.createdAt),
    updatedAt:
      doc.updatedAt instanceof Date
        ? doc.updatedAt.toISOString()
        : String(doc.updatedAt),
  };

  if (doc.description !== undefined && doc.description !== null && doc.description !== "") {
    event.description = doc.description;
  }
  if (doc.expectedLoad !== undefined && doc.expectedLoad !== null) {
    event.expectedLoad = doc.expectedLoad;
  }
  if (doc.priority !== undefined && doc.priority !== null) {
    event.priority = doc.priority;
  }

  return event;
}

// Attach mapping method to Mongoose document instance
scheduledEventSchema.methods.toScheduledEvent = function (
  this: IScheduledEventDocument
): ScheduledEvent {
  return mapDocumentToScheduledEvent(this);
};

// ── Model Registration (Reload Safe) ─────────────────────────────────────────

export const ScheduledEventModel: Model<IScheduledEventDocument> =
  (mongoose.models["ScheduledEvent"] as Model<IScheduledEventDocument>) ||
  model<IScheduledEventDocument>("ScheduledEvent", scheduledEventSchema);
