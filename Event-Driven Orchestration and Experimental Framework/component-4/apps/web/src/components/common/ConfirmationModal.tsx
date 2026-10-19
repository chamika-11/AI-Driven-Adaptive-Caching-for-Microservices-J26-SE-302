// ─────────────────────────────────────────────────────────────────────────────
// Confirmation Modal Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Accessible, reusable dialog for confirming destructive or lifecycle actions.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useEffect, useRef } from "react";

export interface ConfirmationModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  details?: string;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "danger" | "warning" | "primary";
  isPending?: boolean;
  errorMessage?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  title,
  message,
  details,
  confirmLabel,
  cancelLabel = "Cancel",
  variant = "danger",
  isPending = false,
  errorMessage = null,
  onConfirm,
  onCancel,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  // Focus trap & Escape key listener
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isPending) {
        onCancel();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    // Focus confirm button when opened
    confirmBtnRef.current?.focus();

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, isPending, onCancel]);

  if (!isOpen) return null;

  const getVariantStyles = () => {
    switch (variant) {
      case "danger":
        return {
          btnClass: "btn-confirm-danger",
          icon: "⚠️",
          iconBg: "#fee2e2",
          iconColor: "#b91c1c",
        };
      case "warning":
        return {
          btnClass: "btn-confirm-warning",
          icon: "⚡",
          iconBg: "#fef3c7",
          iconColor: "#b45309",
        };
      default:
        return {
          btnClass: "btn-confirm-primary",
          icon: "ℹ️",
          iconBg: "#eff6ff",
          iconColor: "#1d4ed8",
        };
    }
  };

  const { btnClass, icon, iconBg, iconColor } = getVariantStyles();

  return (
    <div
      className="modal-backdrop confirmation-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isPending) {
          onCancel();
        }
      }}
      role="presentation"
    >
      <div
        className="modal-container confirmation-dialog-container"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirmation-title"
        aria-describedby="confirmation-desc"
      >
        <div className="confirmation-body">
          <div
            className="confirmation-icon-wrapper"
            style={{ backgroundColor: iconBg, color: iconColor }}
            aria-hidden="true"
          >
            {icon}
          </div>

          <div className="confirmation-content">
            <h3 id="confirmation-title" className="confirmation-title">
              {title}
            </h3>
            <p id="confirmation-desc" className="confirmation-message">
              {message}
            </p>
            {details && <p className="confirmation-details">{details}</p>}

            {/* Error display if operation failed */}
            {errorMessage && (
              <div className="confirmation-error-alert" role="alert">
                <span className="error-icon" aria-hidden="true">
                  ✕
                </span>
                <span>{errorMessage}</span>
              </div>
            )}
          </div>
        </div>

        <div className="confirmation-footer">
          <button
            type="button"
            className="btn btn-secondary btn-confirm-cancel"
            onClick={onCancel}
            disabled={isPending}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmBtnRef}
            type="button"
            className={`btn ${btnClass}`}
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? (
              <span className="btn-spinner-label">
                <span className="mini-spinner" aria-hidden="true" />
                Processing…
              </span>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
