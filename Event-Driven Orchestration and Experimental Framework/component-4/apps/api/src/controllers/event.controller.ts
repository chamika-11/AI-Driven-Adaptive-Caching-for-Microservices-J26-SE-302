// ─────────────────────────────────────────────────────────────────────────────
// Event Management Controller — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Handles Express request and response serialization for scheduled events.
// Conforms to shared API response contracts (EventResponse, EventListResponse).
// ─────────────────────────────────────────────────────────────────────────────

import type { Request, Response } from "express";
import type { EventResponse, EventListResponse } from "@component4/shared";
import { EventService, type IEventService } from "../services/index.js";

export class EventController {
  private readonly service: IEventService;

  constructor(service: IEventService = new EventService()) {
    this.service = service;
  }

  /**
   * POST /api/events
   * Creates a new scheduled business event.
   * Status: 201 Created
   * Response: EventResponse { event: ScheduledEvent }
   */
  public create = async (req: Request, res: Response): Promise<void> => {
    const event = await this.service.createEvent(req.body);
    const response: EventResponse = { event };
    res.status(201).json(response);
  };

  /**
   * GET /api/events
   * Lists scheduled events with pagination, sorting, and filtering.
   * Status: 200 OK
   * Response: EventListResponse { events: ScheduledEvent[], pagination: PaginationMeta }
   */
  public list = async (req: Request, res: Response): Promise<void> => {
    const result: EventListResponse = await this.service.listEvents(req.query);
    res.status(200).json(result);
  };

  /**
   * GET /api/events/:eventId
   * Retrieves a single scheduled event by application-level eventId.
   * Status: 200 OK
   * Response: EventResponse { event: ScheduledEvent }
   */
  public getById = async (req: Request, res: Response): Promise<void> => {
    const rawId = Array.isArray(req.params.eventId) ? req.params.eventId[0] : req.params.eventId;
    const event = await this.service.getEventById(rawId ?? "");
    const response: EventResponse = { event };
    res.status(200).json(response);
  };

  /**
   * PATCH /api/events/:eventId
   * Partially updates a scheduled event.
   * Status: 200 OK
   * Response: EventResponse { event: ScheduledEvent }
   */
  public update = async (req: Request, res: Response): Promise<void> => {
    const rawId = Array.isArray(req.params.eventId) ? req.params.eventId[0] : req.params.eventId;
    const event = await this.service.updateEvent(rawId ?? "", req.body);
    const response: EventResponse = { event };
    res.status(200).json(response);
  };

  /**
   * POST /api/events/:eventId/cancel
   * Cancels a scheduled event by application-level eventId.
   * Status: 200 OK
   * Response: EventResponse { event: ScheduledEvent }
   */
  public cancel = async (req: Request, res: Response): Promise<void> => {
    const rawId = Array.isArray(req.params.eventId) ? req.params.eventId[0] : req.params.eventId;
    const event = await this.service.cancelEvent(rawId ?? "");
    const response: EventResponse = { event };
    res.status(200).json(response);
  };

  /**
   * DELETE /api/events/:eventId
   * Deletes a scheduled event by application-level eventId.
   * Status: 200 OK
   */
  public delete = async (req: Request, res: Response): Promise<void> => {
    const rawId = Array.isArray(req.params.eventId) ? req.params.eventId[0] : req.params.eventId;
    const eventId = await this.service.deleteEvent(rawId ?? "");
    res.status(200).json({
      success: true,
      message: `Scheduled event '${eventId}' was deleted successfully`,
      eventId,
    });
  };
}
