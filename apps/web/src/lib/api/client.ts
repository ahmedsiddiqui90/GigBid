// Typed client generated from FastAPI's OpenAPI schema (src/lib/api/schema.d.ts, do not hand-edit).
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type JobRow = components["schemas"]["JobRow"];
export type Me = components["schemas"]["Me"];
export type Health = components["schemas"]["Health"];
export type ResolveIn = components["schemas"]["ResolveIn"];

export const api = createClient<paths>({ baseUrl: "", credentials: "include" });

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Unwraps an openapi-fetch result, throwing a readable error. */
export async function unwrap<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || !response.ok) {
    const detail = (error as { detail?: unknown })?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return data as T;
}
