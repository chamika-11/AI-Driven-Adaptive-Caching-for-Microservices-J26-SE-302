// ─────────────────────────────────────────────────────────────────────────────
// API Documentation Gateway Routes — Component 4 API
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Proxies OpenAPI/Swagger documentation requests to the Python FastAPI Ingestion Service.
// ─────────────────────────────────────────────────────────────────────────────

import { Router, type Request, type Response } from "express";

export const docsRouter = Router();

const getIngestionBaseUrl = (): string => {
  return (process.env.INGESTION_SERVICE_URL || "http://127.0.0.1:8001").replace(/\/+$/, "");
};

docsRouter.all("*", async (req: Request, res: Response): Promise<void> => {
  const baseUrl = getIngestionBaseUrl();
  const targetPath = req.url === "/" ? "" : req.url;
  const targetUrl = `${baseUrl}/api/v1${targetPath}`;

  try {
    const headers = new Headers();
    for (const [key, val] of Object.entries(req.headers)) {
      if (val && key.toLowerCase() !== "host" && key.toLowerCase() !== "content-length") {
        headers.set(key, Array.isArray(val) ? val.join(",") : String(val));
      }
    }

    const isGetOrHead = req.method === "GET" || req.method === "HEAD";
    let body: any = undefined;

    if (!isGetOrHead) {
      if (req.is("application/json") && req.body && Object.keys(req.body).length > 0) {
        body = JSON.stringify(req.body);
        headers.set("content-type", "application/json");
      } else {
        body = req;
      }
    }

    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
      duplex: "half",
    } as RequestInit);

    res.status(response.status);
    response.headers.forEach((value, name) => {
      // Exclude transfer-encoding to avoid duplicate chunking errors in Express
      if (name.toLowerCase() !== "transfer-encoding") {
        res.setHeader(name, value);
      }
    });

    const buffer = await response.arrayBuffer();
    res.send(Buffer.from(buffer));
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    res.status(503).json({
      success: false,
      statusCode: 503,
      message: `API Ingestion Service unreachable at ${baseUrl}: ${message}. Ensure the Python FastAPI service is running on port 8001.`,
    });
  }
});
