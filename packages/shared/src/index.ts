/**
 * @panelmind/shared
 *
 * Shared TypeScript types and Zod schemas for the PanelMind web app and API.
 *
 * This package is intentionally minimal in Tier 0a. The actual shared types
 * (Pydantic ↔ Zod parity) are introduced in Tier 0b once the API surface is
 * stabilized.
 *
 * If you're reading this in the future: see `src/schemas/` for the canonical
 * definitions.
 */

export const PANELMIND_VERSION = "0.1.0";

/** All agent persona identifiers known to the panel. */
export const PERSONA_IDS = [
  "vc",
  "enthusiastic",
  "hostile",
  "expert",
  "beginner",
  "interviewer",
] as const;

export type PersonaId = (typeof PERSONA_IDS)[number];

/** The three evaluation modes a user can pick. */
export const MODES = ["spark", "venture", "reality"] as const;
export type Mode = (typeof MODES)[number];

/** All LLM providers PanelMind can route to. */
export const PROVIDERS = [
  "anthropic",
  "openai",
  "gemini",
  "groq",
  "ollama",
] as const;
export type Provider = (typeof PROVIDERS)[number];
