// ─────────────────────────────────────────────────────────────────────────────
// API Documentation Ingestion View — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Ingestion interface for OpenAPI 3.x and Swagger 2.0 specifications.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useRef } from "react";
import {
  uploadSpecification,
  type IngestionResponse,
  type NormalizedEndpoint,
} from "../../services/docs.service.js";

interface ApiDocIngestionViewProps {
  onBackToDashboard: () => void;
}

export const ApiDocIngestionView: React.FC<ApiDocIngestionViewProps> = ({
  onBackToDashboard,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [ingestionResult, setIngestionResult] = useState<IngestionResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (selectedFile: File) => {
    setFile(selectedFile);
    setErrorMessage(null);
    setIngestionResult(null);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setErrorMessage("Please select an OpenAPI or Swagger file (.json, .yaml, .yml) to upload.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);
    try {
      const result = await uploadSpecification(file);
      setIngestionResult(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const getMethodBadgeClass = (method: string): string => {
    switch (method.toUpperCase()) {
      case "GET":
        return "badge-method-get";
      case "POST":
        return "badge-method-post";
      case "PUT":
        return "badge-method-put";
      case "DELETE":
        return "badge-method-delete";
      case "PATCH":
        return "badge-method-patch";
      default:
        return "badge-method-other";
    }
  };

  return (
    <div className="ingestion-container" role="region" aria-label="API Documentation Ingestion">
      {/* Header */}
      <div className="ingestion-header">
        <div>
          <span className="placeholder-badge">Scheduled for Part 4.x Implementation</span>
          <h3 className="placeholder-title" style={{ fontSize: "1.25rem", fontWeight: 700, margin: "6px 0 4px" }}>
            API Knowledge & OpenAPI Ingestion
          </h3>
          <p className="ingestion-subtitle">
            Upload service documentation to extract normalized endpoints and link temporal events to cache targets.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onBackToDashboard}
          aria-label="Return to Event Dashboard"
        >
          ← Return to Events
        </button>
      </div>

      {/* Upload Form Card */}
      <div className="ingestion-card">
        <form onSubmit={handleSubmit} className="upload-form">
          <div
            className={`dropzone ${isDragOver ? "dropzone-active" : ""}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="File Upload Dropzone"
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleInputChange}
              accept=".json,.yaml,.yml,application/json,application/x-yaml,text/yaml"
              style={{ display: "none" }}
              data-testid="file-upload-input"
            />
            <div className="dropzone-icon">📄</div>
            <p className="dropzone-text">
              {file ? (
                <strong>Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)</strong>
              ) : (
                <>
                  <strong>Click to browse</strong> or drag & drop specification here
                </>
              )}
            </p>
            <p className="dropzone-hint">
              Supports OpenAPI 3.0, 3.1, and Swagger 2.0 (JSON or YAML, up to 5 MB)
            </p>
          </div>

          <div className="upload-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!file || isLoading}
              aria-label="Upload and Ingest Specification"
            >
              {isLoading ? "Validating & Ingesting..." : "Upload & Normalize Spec"}
            </button>
            {file && !isLoading && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setFile(null);
                  setIngestionResult(null);
                  setErrorMessage(null);
                }}
              >
                Clear
              </button>
            )}
          </div>
        </form>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="loading-container" role="status" aria-live="polite">
          <div className="spinner" />
          <p style={{ marginTop: "12px", color: "var(--text-muted)" }}>
            Parsing document structure, validating security boundaries, and extracting endpoints...
          </p>
        </div>
      )}

      {/* Error Message */}
      {errorMessage && !isLoading && (
        <div className="error-card" role="alert">
          <div className="error-title">⚠️ Specification Ingestion Error</div>
          <div className="error-message">{errorMessage}</div>
        </div>
      )}

      {/* Success & Normalized Endpoints Table */}
      {ingestionResult && ingestionResult.success && ingestionResult.document && !isLoading && (
        <div className="ingestion-results">
          <div className="success-banner" role="status">
            <h3>✓ Ingestion Completed Successfully</h3>
            <p>{ingestionResult.message}</p>
          </div>

          {/* Document Summary Card */}
          <div className="meta-card">
            <h4>Specification Metadata</h4>
            <div className="meta-grid">
              <div className="meta-item">
                <span className="meta-label">Service Name:</span>
                <span className="meta-value"><strong>{ingestionResult.document.service_name}</strong></span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Title & Version:</span>
                <span className="meta-value">{ingestionResult.document.title} (v{ingestionResult.document.version})</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Format:</span>
                <span className="meta-value">{ingestionResult.document.spec_format.toUpperCase()} {ingestionResult.document.spec_version}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Provenance Hash:</span>
                <span className="meta-value font-mono" title={ingestionResult.document.document_id}>
                  {ingestionResult.document.document_id.substring(0, 16)}...
                </span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Extracted Endpoints:</span>
                <span className="meta-value"><strong>{ingestionResult.endpoints_count}</strong></span>
              </div>
              {ingestionResult.document.base_urls.length > 0 && (
                <div className="meta-item" style={{ gridColumn: "1 / -1" }}>
                  <span className="meta-label">Base URLs / Servers:</span>
                  <span className="meta-value">{ingestionResult.document.base_urls.join(", ")}</span>
                </div>
              )}
            </div>
          </div>

          {/* Endpoints Table */}
          <div className="table-card">
            <h4 style={{ padding: "16px 20px 8px" }}>Normalized Service Endpoints</h4>
            <div className="table-wrapper">
              <table className="table" aria-label="Normalized Endpoints Table">
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>Path</th>
                    <th>Operation ID</th>
                    <th>Summary</th>
                    <th>Parameters</th>
                    <th>Responses</th>
                  </tr>
                </thead>
                <tbody>
                  {ingestionResult.endpoints.map((ep) => (
                    <tr key={ep.id}>
                      <td>
                        <span className={`method-badge ${getMethodBadgeClass(ep.method)}`}>
                          {ep.method}
                        </span>
                      </td>
                      <td className="font-mono"><strong>{ep.path}</strong></td>
                      <td>{ep.operation_id || <span className="text-muted">—</span>}</td>
                      <td>{ep.summary || ep.description || <span className="text-muted">—</span>}</td>
                      <td>
                        {ep.parameters.length > 0 ? (
                          <span className="badge-pill">{ep.parameters.length} param(s)</span>
                        ) : (
                          <span className="text-muted">None</span>
                        )}
                      </td>
                      <td>
                        {ep.responses.map((r) => (
                          <span key={r.status_code} className="badge-pill" style={{ marginRight: "4px" }}>
                            {r.status_code}
                          </span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
