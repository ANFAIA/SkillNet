/**
 * Thin HTTP client for `/ext/v1`. This is the ONLY way this package talks to
 * SkillNet: plain `fetch` calls against the FastAPI backend, carrying the caller's
 * API key as a Bearer token. No PostgreSQL driver, no direct database access, no
 * business logic duplicated from `apps/skillnet-api` — every rule (org scoping, level
 * validation, gap thresholds, ...) lives server-side and this client just relays it.
 */
import { toApiError } from "./errors.js";

export interface SkillCategory {
  id: string;
  name: string;
  skills: Array<{ id: string; name: string; description?: string | null }>;
}

export interface WhoKnowsResponse {
  skill: string;
  employees: Array<{
    user_id: string;
    full_name: string;
    level: string;
    source: string;
    last_assessed_at?: string | null;
  }>;
  [key: string]: unknown;
}

export interface GapReport {
  gaps: Array<{
    skill: { id: string; name: string; category?: string };
    total_users: number;
    users_at_level: number;
    coverage_ratio: number;
    gap_severity: string;
    users_below?: Array<{ id: string; full_name: string; current_level: string }>;
  }>;
  [key: string]: unknown;
}

export interface UserSkill {
  skill_id: string;
  skill_name: string;
  category?: string;
  level: string;
  source: string;
  last_assessed_at?: string | null;
}

export interface CreateCourseParams {
  title: string;
  document_id?: string;
  intent_density?: number;
  enroll_user_id?: string;
  generate_artifacts?: string[];
  artifact_node_limit?: number;
}

export interface CreateCourseResult {
  course_id: string;
  title: string;
  schema_status: string;
  schema_version: number;
  node_count: number;
  packs_ready: number;
  packs_all_ready: boolean;
  packs_summary: string;
  nodes: Array<{ node_id: string; title: string; status: string }>;
  reviewed: boolean;
  validated: boolean;
  enrolled_user_id: string | null;
  prewarm_spawned: boolean;
  artifacts: Array<{ artifact_id: string; node_id: string; kind: string; status: string }>;
  warnings: string[];
  [key: string]: unknown;
}

export interface SkillNetClientOptions {
  apiUrl: string;
  apiKey: string;
  requestTimeoutMs?: number;
  createCourseTimeoutMs?: number;
}

export class SkillNetClient {
  private readonly apiUrl: string;
  private readonly apiKey: string;
  private readonly requestTimeoutMs: number;
  private readonly createCourseTimeoutMs: number;

  constructor(options: SkillNetClientOptions) {
    this.apiUrl = options.apiUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.requestTimeoutMs = options.requestTimeoutMs ?? 30_000;
    this.createCourseTimeoutMs = options.createCourseTimeoutMs ?? 600_000;
  }

  async listSkills(params: { category?: string; search?: string } = {}): Promise<
    SkillCategory[]
  > {
    return this.get("/ext/v1/skills", params, this.requestTimeoutMs);
  }

  async whoKnows(params: {
    skill: string;
    min_level?: string;
    limit?: number;
  }): Promise<WhoKnowsResponse> {
    return this.get("/ext/v1/skills/who-knows", params, this.requestTimeoutMs);
  }

  async getGap(params: {
    skill?: string;
    min_level?: string;
    threshold?: number;
  } = {}): Promise<GapReport> {
    return this.get("/ext/v1/skills/gaps", params, this.requestTimeoutMs);
  }

  async getUserSkills(userId: string): Promise<UserSkill[]> {
    return this.get(
      `/ext/v1/users/${encodeURIComponent(userId)}/skills`,
      {},
      this.requestTimeoutMs
    );
  }

  async createCourse(params: CreateCourseParams): Promise<CreateCourseResult> {
    return this.post("/ext/v1/courses/full", params, this.createCourseTimeoutMs);
  }

  // -- internals ---------------------------------------------------------------------

  private async get<T>(
    path: string,
    query: Record<string, string | number | undefined>,
    timeoutMs: number
  ): Promise<T> {
    const url = new URL(this.apiUrl + path);
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
    const response = await this.fetchWithTimeout(url, { method: "GET" }, timeoutMs);
    if (!response.ok) {
      throw await toApiError(response);
    }
    return (await response.json()) as T;
  }

  private async post<T>(path: string, body: unknown, timeoutMs: number): Promise<T> {
    const url = new URL(this.apiUrl + path);
    const response = await this.fetchWithTimeout(
      url,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      },
      timeoutMs
    );
    if (!response.ok) {
      throw await toApiError(response);
    }
    return (await response.json()) as T;
  }

  private async fetchWithTimeout(
    url: URL,
    init: RequestInit,
    timeoutMs: number
  ): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, {
        ...init,
        signal: controller.signal,
        headers: {
          ...(init.headers ?? {}),
          authorization: `Bearer ${this.apiKey}`,
        },
      });
    } finally {
      clearTimeout(timer);
    }
  }
}
