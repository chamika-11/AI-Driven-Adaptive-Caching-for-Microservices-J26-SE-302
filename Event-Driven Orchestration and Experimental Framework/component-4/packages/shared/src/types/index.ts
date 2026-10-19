/**
 * Barrel export for all shared type definitions.
 *
 * Each domain module re-exports its public surface from here so that
 * consumers can import from "@component4/shared" without reaching into
 * internal paths.
 */

export * from "./event.types.js";
