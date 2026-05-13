import type {
  ActivateSectionResponse,
  AuthPayload,
  CheckpointAttemptResponse,
  Concept,
  Learner,
  LessonWorkspace,
  LessonPlan,
  ReviewItem,
  Session,
  StudySessionResponse,
  SubmitTurnResponse,
  SupplementalMaterial,
  TopicProgress
} from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type RequestOptions = {
  authenticated?: boolean;
};

const CSRF_COOKIE_NAME = "adaptive_tutor_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";

function readCookie(name: string) {
  if (typeof document === "undefined") {
    return null;
  }
  const cookie = document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${name}=`));
  return cookie ? decodeURIComponent(cookie.split("=", 2)[1] ?? "") : null;
}

// Auth is fully cookie-based: the server sets and clears the HttpOnly session
// cookie in response headers, and the browser sends it automatically via
// `credentials: "include"`.  These functions exist so call sites in the UI
// can communicate intent without knowing the transport detail.  If auth is
// ever migrated to a header-based token these are the only two places to update.
export function setAuthToken(_token: string) {
  // No-op: token is already stored in the HttpOnly cookie set by the server.
}

export function clearAuthSession() {
  // No-op: the server clears the cookie on the logout response.
}

async function request<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
  void options;
  const method = (init?.method ?? "GET").toUpperCase();
  const csrfToken = method === "GET" || method === "HEAD" || method === "OPTIONS" ? null : readCookie(CSRF_COOKIE_NAME);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { [CSRF_HEADER_NAME]: csrfToken } : {}),
      ...(init?.headers ?? {})
    },
    cache: "no-store",
    credentials: "include"
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
  goal?: string;
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
  try {
    return await request<AuthPayload>("/auth/me");
  } catch {
    return null;
  }
}

export async function logout() {
  return request<{ status: string }>("/auth/logout", { method: "POST" });
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

export function createStudySession(
  learnerId: string,
  payload: { prompt: string; mode?: "learn" | "ask" | "test" | "review" }
) {
  return request<StudySessionResponse>(`/learners/${learnerId}/study-session`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getSession(sessionId: string) {
  return request<Session>(`/sessions/${sessionId}`);
}

export async function getLatestSession(learnerId: string) {
  try {
    return await request<Session>(`/learners/${learnerId}/sessions/latest`);
  } catch {
    return null;
  }
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

export function completeReview(reviewId: string, answer: string) {
  return request<ReviewItem>(`/reviews/${reviewId}/complete`, {
    method: "POST",
    body: JSON.stringify({ answer })
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

export function getLessonPlan(learnerId: string, topic: string) {
  return request<LessonPlan>(
    `/learners/${learnerId}/lesson-plan?topic=${encodeURIComponent(topic)}`
  );
}

export function getLessonWorkspace(learnerId: string) {
  return request<LessonWorkspace>(`/learners/${learnerId}/workspace`);
}

export function submitCheckpointAttempt(
  learnerId: string,
  checkpointId: string,
  selectedOptionId: string
) {
  return request<CheckpointAttemptResponse>(`/learners/${learnerId}/checkpoints/${checkpointId}/attempt`, {
    method: "POST",
    body: JSON.stringify({ selected_option_id: selectedOptionId })
  });
}

export function activateCourseSection(
  learnerId: string,
  courseId: string,
  sectionId: string
) {
  return request<ActivateSectionResponse>(`/learners/${learnerId}/courses/${courseId}/sections/activate`, {
    method: "POST",
    body: JSON.stringify({ section_id: sectionId })
  });
}

export function createConcept(payload: {
  slug: string;
  title: string;
  description: string;
  subject: string;
  prerequisites: string[];
  objectives?: string[];
}) {
  return request<Concept>("/curriculum/concepts", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
