// ─────────────────────────────────────────────────────────────────────────────
// Date & Time Formatting Utilities — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Formats ISO 8601 timestamps with explicit timezone transparency.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Formats an ISO 8601 datetime string into a human-readable format,
 * clearly displaying both the localized time and timezone offset.
 *
 * Example output: "Nov 20, 2026, 08:00 UTC" or "Nov 20, 2026, 13:30 (GMT+5:30)"
 */
export function formatDateTime(isoString?: string | null): string {
  if (!isoString) {
    return "—";
  }

  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) {
      return isoString;
    }

    const datePart = date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });

    const timePart = date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });

    // Extract timezone abbreviation or offset
    const timeZoneName = Intl.DateTimeFormat("en-US", {
      timeZoneName: "short",
    })
      .formatToParts(date)
      .find((p) => p.type === "timeZoneName")?.value ?? "UTC";

    return `${datePart}, ${timePart} ${timeZoneName}`;
  } catch {
    return isoString;
  }
}

/**
 * Formats a duration in minutes into a friendly string (e.g. "45m", "2h", "1d 4h").
 */
export function formatDurationMinutes(minutes?: number | null): string {
  if (minutes === undefined || minutes === null || isNaN(minutes)) {
    return "—";
  }

  if (minutes < 60) {
    return `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours < 24) {
    return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  }

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
}

/**
 * Returns today's date formatted nicely for the top header.
 */
export function getHeaderCurrentDate(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Returns formatted offset string like "+05:30", "-04:00", or "Z" for a given date.
 */
export function getLocalTimezoneOffset(date: Date = new Date()): string {
  const offsetMinutes = -date.getTimezoneOffset();
  if (offsetMinutes === 0) return "Z";
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absMinutes = Math.abs(offsetMinutes);
  const hours = String(Math.floor(absMinutes / 60)).padStart(2, "0");
  const minutes = String(absMinutes % 60).padStart(2, "0");
  return `${sign}${hours}:${minutes}`;
}

/**
 * Returns a human-friendly timezone description, e.g. "Asia/Colombo (UTC+05:30)" or "UTC".
 */
export function getLocalTimezoneLabel(): string {
  try {
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const offset = getLocalTimezoneOffset();
    return `${timeZone} (${offset === "Z" ? "UTC" : `UTC${offset}`})`;
  } catch {
    return `UTC${getLocalTimezoneOffset()}`;
  }
}

/**
 * Converts an ISO 8601 string to a datetime-local input string (YYYY-MM-DDTHH:mm).
 * Preserves the actual instant in the user's local timezone.
 */
export function isoToDatetimeLocal(isoString?: string | null): string {
  if (!isoString) return "";
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

/**
 * Converts a datetime-local string (YYYY-MM-DDTHH:mm) to a valid ISO 8601 string with explicit timezone offset.
 */
export function datetimeLocalToIso(datetimeLocal: string): string {
  if (!datetimeLocal || typeof datetimeLocal !== "string") return "";
  const [datePart, timePart] = datetimeLocal.trim().split("T");
  if (!datePart || !timePart) return "";
  const [year, month, day] = datePart.split("-").map(Number);
  const [hours, minutes] = timePart.split(":").map(Number);
  const localDate = new Date(year, month - 1, day, hours, minutes, 0);
  if (isNaN(localDate.getTime())) return "";
  const offset = getLocalTimezoneOffset(localDate);
  return `${datePart}T${timePart}:00${offset}`;
}

