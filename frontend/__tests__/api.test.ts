import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { login, logout, signup, getCurrentAuth } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
  });
}

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}`;
}

function clearCookie(name: string) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("login", () => {
  beforeEach(() => {
    clearCookie("adaptive_tutor_csrf");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends POST to /auth/login with JSON body", async () => {
    const payload = { token: "tok", account: { id: "a1", email: "x@x.com", learner_id: "l1", is_admin: false }, learner: { id: "l1", name: "X", goal: "learn", skills: {}, objective_states: {}, misconceptions: [], learning_style: null } };
    global.fetch = mockFetch(200, payload);

    await login({ email: "x@x.com", password: "secret" });

    expect(fetch).toHaveBeenCalledOnce();
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ email: "x@x.com", password: "secret" });
  });

  it("attaches CSRF token header when cookie is present for non-GET requests", async () => {
    setCookie("adaptive_tutor_csrf", "csrf-abc");
    const payload = { token: "tok", account: { id: "a1", email: "x@x.com", learner_id: "l1", is_admin: false }, learner: { id: "l1", name: "X", goal: "learn", skills: {}, objective_states: {}, misconceptions: [], learning_style: null } };
    global.fetch = mockFetch(200, payload);

    await login({ email: "x@x.com", password: "secret" });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-abc");
  });

  it("throws with the server detail message on 401", async () => {
    global.fetch = mockFetch(401, { detail: "Invalid credentials" });

    await expect(login({ email: "bad@x.com", password: "wrong" })).rejects.toThrow("Invalid credentials");
  });

  it("throws with raw text when response is not JSON", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve("Internal Server Error"),
    });

    await expect(login({ email: "x@x.com", password: "p" })).rejects.toThrow("Internal Server Error");
  });
});

describe("logout", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends POST to /auth/logout", async () => {
    global.fetch = mockFetch(200, { status: "ok" });

    await logout();

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/auth/logout");
    expect(init.method).toBe("POST");
  });
});

describe("signup", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends name, email, password, goal, initial_topic", async () => {
    const payload = { token: "tok", account: { id: "a1", email: "new@x.com", learner_id: "l1", is_admin: false }, learner: { id: "l1", name: "New", goal: "algebra", skills: {}, objective_states: {}, misconceptions: [], learning_style: null } };
    global.fetch = mockFetch(200, payload);

    await signup({ name: "New", email: "new@x.com", password: "pw", goal: "algebra", initial_topic: "algebra" });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.name).toBe("New");
    expect(body.email).toBe("new@x.com");
    expect(body.goal).toBe("algebra");
    expect(body.initial_topic).toBe("algebra");
  });

  it("throws 409 detail on duplicate account", async () => {
    global.fetch = mockFetch(409, { detail: "Account already exists" });

    await expect(signup({ name: "X", email: "dup@x.com", password: "pw" })).rejects.toThrow("Account already exists");
  });
});

describe("getCurrentAuth", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns null when the server returns 401", async () => {
    global.fetch = mockFetch(401, { detail: "Missing session" });

    const result = await getCurrentAuth();

    expect(result).toBeNull();
  });

  it("returns the auth payload on success", async () => {
    const payload = { token: "", account: { id: "a1", email: "me@x.com", learner_id: "l1", is_admin: false }, learner: { id: "l1", name: "Me", goal: "learn", skills: {}, objective_states: {}, misconceptions: [], learning_style: null } };
    global.fetch = mockFetch(200, payload);

    const result = await getCurrentAuth();

    expect(result).not.toBeNull();
    expect(result?.account.email).toBe("me@x.com");
  });
});

describe("GET requests do not include CSRF header", () => {
  beforeEach(() => {
    setCookie("adaptive_tutor_csrf", "csrf-xyz");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    clearCookie("adaptive_tutor_csrf");
  });

  it("omits X-CSRF-Token on GET /auth/me", async () => {
    const payload = { token: "", account: { id: "a1", email: "me@x.com", learner_id: "l1", is_admin: false }, learner: { id: "l1", name: "Me", goal: "learn", skills: {}, objective_states: {}, misconceptions: [], learning_style: null } };
    global.fetch = mockFetch(200, payload);

    await getCurrentAuth();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });
});
