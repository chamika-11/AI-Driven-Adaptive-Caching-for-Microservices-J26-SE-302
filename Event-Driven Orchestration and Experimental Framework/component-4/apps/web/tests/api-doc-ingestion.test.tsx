import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ApiDocIngestionView } from "../src/components/dashboard/ApiDocIngestionView.js";

describe("ApiDocIngestionView", () => {
  const mockOnBackToDashboard = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders upload dropzone and header", () => {
    render(<ApiDocIngestionView onBackToDashboard={mockOnBackToDashboard} />);

    expect(
      screen.getByRole("heading", { level: 3, name: /api knowledge & openapi ingestion/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/scheduled for part 4.x implementation/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /file upload dropzone/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload and ingest specification/i })).toBeDisabled();
  });

  it("calls onBackToDashboard when return button is clicked", () => {
    render(<ApiDocIngestionView onBackToDashboard={mockOnBackToDashboard} />);

    const backBtn = screen.getByRole("button", { name: /return to event dashboard/i });
    fireEvent.click(backBtn);
    expect(mockOnBackToDashboard).toHaveBeenCalledTimes(1);
  });

  it("enables upload button when a file is selected and uploads successfully", async () => {
    const mockIngestionResponse = {
      success: true,
      message: "Successfully ingested OPENAPI_3 specification 'Order API' with 2 endpoint(s).",
      document: {
        document_id: "a1b2c3d4e5f67890123456789012345678901234567890123456789012345678",
        title: "Order API",
        version: "1.0.0",
        service_name: "order-api",
        spec_format: "openapi_3",
        spec_version: "3.0.3",
        base_urls: ["https://api.orders.example.com"],
        filename: "openapi.json",
        file_size_bytes: 1024,
      },
      endpoints_count: 2,
      endpoints: [
        {
          id: "ep1",
          document_id: "a1b2c3d4e5f67890",
          service_name: "order-api",
          path: "/orders",
          method: "GET",
          operation_id: "listOrders",
          summary: "List all orders",
          tags: ["Orders"],
          parameters: [],
          responses: [{ status_code: "200" }],
          extracted_at: "2026-10-19T00:00:00Z",
        },
        {
          id: "ep2",
          document_id: "a1b2c3d4e5f67890",
          service_name: "order-api",
          path: "/orders",
          method: "POST",
          operation_id: "createOrder",
          summary: "Create order",
          tags: ["Orders"],
          parameters: [],
          responses: [{ status_code: "201" }],
          extracted_at: "2026-10-19T00:00:00Z",
        },
      ],
      warnings: [],
      errors: [],
    };

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => mockIngestionResponse,
    });

    render(<ApiDocIngestionView onBackToDashboard={mockOnBackToDashboard} />);

    const file = new File(['{"openapi":"3.0.0"}'], "openapi.json", {
      type: "application/json",
    });

    const fileInput = screen.getByTestId("file-upload-input");
    fireEvent.change(fileInput, { target: { files: [file] } });

    const submitBtn = screen.getByRole("button", { name: /upload and ingest specification/i });
    expect(submitBtn).not.toBeDisabled();

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/ingestion completed successfully/i)).toBeInTheDocument();
      expect(screen.getAllByText(/order api/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText("/orders").length).toBeGreaterThan(0);
      expect(screen.getByText("listOrders")).toBeInTheDocument();
      expect(screen.getByText("createOrder")).toBeInTheDocument();
    });
  });

  it("displays validation error message when server rejects upload", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({
        success: false,
        message: "Malformed JSON specification: Unterminated string at line 4",
      }),
    });

    render(<ApiDocIngestionView onBackToDashboard={mockOnBackToDashboard} />);

    const file = new File(['{"openapi": broken'], "broken.json", {
      type: "application/json",
    });

    const fileInput = screen.getByTestId("file-upload-input");
    fireEvent.change(fileInput, { target: { files: [file] } });

    const submitBtn = screen.getByRole("button", { name: /upload and ingest specification/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(
        screen.getByText(/malformed json specification: unterminated string at line 4/i)
      ).toBeInTheDocument();
    });
  });
});
