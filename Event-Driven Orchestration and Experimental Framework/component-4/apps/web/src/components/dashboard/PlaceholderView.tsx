// ─────────────────────────────────────────────────────────────────────────────
// Placeholder View Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
// ─────────────────────────────────────────────────────────────────────────────

import React from "react";
import type { NavTab } from "../layout/Sidebar.js";

interface PlaceholderViewProps {
  tab: NavTab;
  onBackToDashboard: () => void;
}

export const PlaceholderView: React.FC<PlaceholderViewProps> = ({
  tab,
  onBackToDashboard,
}) => {
  const contentMap: Record<
    "api-docs" | "settings",
    { title: string; subtitle: string; description: string; phase: string }
  > = {
    "api-docs": {
      title: "API Knowledge & OpenAPI Ingestion",
      subtitle: "Research Component 4 — Module 3",
      description:
        "The API Knowledge Repository module will ingest service endpoint schemas and microservice routing maps to link scheduled business events with backend cache targets.",
      phase: "Scheduled for Part 4.x Implementation",
    },
    "settings": {
      title: "Framework Settings & Model Configuration",
      subtitle: "Component 4 Configuration & Tuning",
      description:
        "System configuration panel for prewarm window algorithms, feature vector normalization parameters, and Component 3 (Reinforcement Learning) integration endpoints.",
      phase: "Scheduled for Framework Configuration Phase",
    },
  };

  const details =
    tab === "api-docs" || tab === "settings"
      ? contentMap[tab]
      : {
          title: "Module In Development",
          subtitle: "Component 4 Experimental Framework",
          description: "This module is planned for a subsequent research milestone.",
          phase: "Upcoming Milestone",
        };

  return (
    <div className="placeholder-card" role="region" aria-label={details.title}>
      <div className="placeholder-badge">{details.phase}</div>
      <h3 className="placeholder-title">{details.title}</h3>
      <p className="placeholder-subtitle">{details.subtitle}</p>
      <p className="placeholder-description">{details.description}</p>

      <button
        type="button"
        className="btn btn-secondary"
        onClick={onBackToDashboard}
        aria-label="Return to Event Dashboard"
      >
        ← Back to Event Dashboard
      </button>
    </div>
  );
};
