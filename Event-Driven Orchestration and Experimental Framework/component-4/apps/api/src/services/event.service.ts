// ─────────────────────────────────────────────────────────────────────────────
// Event Management Service — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Orchestrates business validation and delegates persistence to the EventRepository.
// Decoupled from Express Request and Response objects.
// ─────────────────────────────────────────────────────────────────────────────

import {
  CreateScheduledEventInputSchema,
  UpdateScheduledEventInputSchema,
  ListEventsQuerySchema,
  type ScheduledEvent,
  type CreateScheduledEventInput,
  type UpdateScheduledEventInput,
  type EventListResponse,
  type ListEventsQuery,
} from "@component4/shared";
import {
  EventRepository,
  type IEventRepository,
} from "../repositories/index.js";
import { BadRequestError, NotFoundError, ConflictError } from "../errors/index.js";

export interface IEventService {
  createEvent(input: unknown): Promise<ScheduledEvent>;
  listEvents(query: unknown): Promise<EventListResponse>;
  getEventById(eventId: string): Promise<ScheduledEvent>;
  updateEvent(eventId: string, input: unknown): Promise<ScheduledEvent>;
  cancelEvent(eventId: string): Promise<ScheduledEvent>;
  deleteEvent(eventId: string): Promise<string>;
}

export class EventService implements IEventService {
  private readonly repository: IEventRepository;

  constructor(repository: IEventRepository = new EventRepository()) {
    this.repository = repository;
  }

  /**
   * Validates create payload and persists scheduled event.
   */
  public async createEvent(input: unknown): Promise<ScheduledEvent> {
    const validated = CreateScheduledEventInputSchema.parse(input);
    return this.repository.create(validated as CreateScheduledEventInput);
  }

  /**
   * Validates query parameters and retrieves paginated events.
   */
  public async listEvents(query: unknown): Promise<EventListResponse> {
    const validated = ListEventsQuerySchema.parse(query);
    return this.repository.list(validated as ListEventsQuery);
  }

  /**
   * Retrieves an event by its application-level eventId.
   * Throws NotFoundError if no matching record exists.
   */
  public async getEventById(eventId: string): Promise<ScheduledEvent> {
    const cleanId = this.validateEventId(eventId);
    const event = await this.repository.findById(cleanId);
    if (!event) {
      throw new NotFoundError(
        `Scheduled event with ID '${cleanId}' was not found`
      );
    }
    return event;
  }

  /**
   * Validates partial update payload and updates the scheduled event.
   * Throws NotFoundError if event does not exist.
   */
  public async updateEvent(
    eventId: string,
    input: unknown
  ): Promise<ScheduledEvent> {
    const cleanId = this.validateEventId(eventId);
    const validated = UpdateScheduledEventInputSchema.parse(input);
    const updated = await this.repository.update(
      cleanId,
      validated as UpdateScheduledEventInput
    );
    if (!updated) {
      throw new NotFoundError(
        `Scheduled event with ID '${cleanId}' was not found`
      );
    }
    return updated;
  }

  /**
   * Cancels a scheduled event by its application-level eventId.
   * Enforces lifecycle transition rules: only SCHEDULED events may be cancelled.
   * Throws ConflictError (409) if status is not SCHEDULED.
   * Throws NotFoundError (404) if event does not exist.
   */
  public async cancelEvent(eventId: string): Promise<ScheduledEvent> {
    const cleanId = this.validateEventId(eventId);
    const existing = await this.repository.findById(cleanId);
    if (!existing) {
      throw new NotFoundError(
        `Scheduled event with ID '${cleanId}' was not found`
      );
    }

    if (existing.status === "CANCELLED") {
      throw new ConflictError(
        `Event '${cleanId}' is already CANCELLED`
      );
    }

    if (existing.status === "COMPLETED") {
      throw new ConflictError(
        `Cannot cancel event '${cleanId}' because it is already COMPLETED`
      );
    }

    if (existing.status === "PROCESSING") {
      throw new ConflictError(
        `Cannot cancel event '${cleanId}' because it is currently PROCESSING`
      );
    }

    if (existing.status !== "SCHEDULED") {
      throw new ConflictError(
        `Cannot cancel event '${cleanId}' with status '${existing.status}'`
      );
    }

    const updated = await this.repository.updateStatus(cleanId, "CANCELLED");
    if (!updated) {
      throw new NotFoundError(
        `Scheduled event with ID '${cleanId}' was not found`
      );
    }
    return updated;
  }

  /**
   * Deletes an event by its application-level eventId.
   * Throws NotFoundError if event does not exist.
   */
  public async deleteEvent(eventId: string): Promise<string> {
    const cleanId = this.validateEventId(eventId);
    const deleted = await this.repository.delete(cleanId);
    if (!deleted) {
      throw new NotFoundError(
        `Scheduled event with ID '${cleanId}' was not found`
      );
    }
    return cleanId;
  }

  /**
   * Validates path parameter eventId.
   */
  private validateEventId(eventId: unknown): string {
    if (!eventId || typeof eventId !== "string" || eventId.trim() === "") {
      throw new BadRequestError("Invalid or missing eventId path parameter");
    }
    return eventId.trim();
  }
}
