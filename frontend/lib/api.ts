import type {
  AuthPayload,
  Concept,
  Learner,
  ReviewItem,
  Session,
  SubmitTurnResponse,
  SupplementalMaterial,
  TopicProgress
} from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const AUTH_TOKEN_KEY = "adaptive-tutor.auth-token";

type RequestOptions = {
  authenticated?: boolean;
};

function readAuthToken() {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthSession() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
  const token = options?.authenticated === false ? null : readAuthToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });

  if (!response.ok) {
    const message = await response.text();
    let detail: string | null = null;
    try {
      const payload = JSON.parse(message) as { detail?: string };
      detail = payload.detail ?? null;
    } catch {
      detail = null;
    }
    throw new Error(detail ?? message ?? `Request failed for ${path}`);
  }

  return (await response.json()) as T;
}

export function signup(payload: {
  email: string;
  password: string;
  name: string;
  goal: string;
  initial_topic?: string;
}) {
  return request<AuthPayload>(
    "/auth/signup",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    { authenticated: false }
  );
}

export function login(payload: { email: string; password: string }) {
  return request<AuthPayload>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    { authenticated: false }
  );
}

export async function getCurrentAuth() {
  const token = readAuthToken();
  if (!token) {
    return null;
  }

  try {
    return await request<AuthPayload>("/auth/me");
  } catch {
    clearAuthSession();
    return null;
  }
}

export async function logout() {
  try {
    return await request<{ status: string }>("/auth/logout", { method: "POST" });
  } finally {
    clearAuthSession();
  }
}

export function createLearner(payload: {
  name: string;
  goal: string;
  initial_topic?: string;
  preferences: {
    verbosity: "low" | "medium" | "high";
    prefers_examples: boolean;
    teaching_style: "socratic" | "direct" | "blended";
  };
}) {
  return request<Learner>(
    "/learners",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    { authenticated: false }
  );
}

export function getLearner(learnerId: string) {
  return request<Learner>(`/learners/${learnerId}`);
}

export function createSession(payload: {
  learner_id: string;
  topic: string;
  mode: "learn" | "ask" | "test" | "review";
}) {
  return request<Session>("/sessions", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getSession(sessionId: string) {
  return request<Session>(`/sessions/${sessionId}`);
}

export function submitTurn(
  sessionId: string,
  payload: { message: string; mode?: "learn" | "ask" | "test" | "review" }
) {
  return request<SubmitTurnResponse>(`/sessions/${sessionId}/turns`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getProgress(learnerId: string, subject?: string) {
  const query = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return request<TopicProgress[]>(`/learners/${learnerId}/progress/objectives${query}`);
}

export function getDueReviews(learnerId: string) {
  return request<ReviewItem[]>(`/learners/${learnerId}/reviews/due`);
}

export function completeReview(reviewId: string, correct: boolean) {
  return request<ReviewItem>(`/reviews/${reviewId}/complete`, {
    method: "POST",
    body: JSON.stringify({ correct })
  });
}

export function getMaterialSuggestions(learnerId: string, topic: string) {
  return request<SupplementalMaterial[]>(
    `/learners/${learnerId}/materials/suggestions?topic=${encodeURIComponent(topic)}`
  );
}

export function getCurriculumRecommendations(learnerId: string, subject?: string) {
  const query = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return request<Concept[]>(`/learners/${learnerId}/curriculum/recommendations${query}`);
}

export function createConcept(payload: {
  slug: string;
  title: string;
  description: string;
  subject: string;
  prerequisites: string[];
  objectives?: string[];
}) {
  return request<Concept>(
    "/curriculum/concepts",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    { authenticated: false }
  );
}
