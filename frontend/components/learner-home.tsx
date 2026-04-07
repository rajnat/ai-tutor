"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useTransition } from "react";
import {
  clearAuthSession,
  completeReview,
  createSession,
  getCurrentAuth,
  getCurriculumRecommendations,
  getDueReviews,
  getLessonPlan,
  getMaterialSuggestions,
  getProgress,
  getSession,
  login,
  logout,
  setAuthToken,
  signup,
  submitTurn
} from "@/lib/api";
import type {
  Account,
  AuthPayload,
  Concept,
  Learner,
  LessonPlan,
  LessonPlanStep,
  ObjectiveProgress,
  ReviewItem,
  Session,
  SupplementalMaterial,
  TopicProgress
} from "@/lib/types";

type AuthMode = "signup" | "login";
type AuthStatus = "loading" | "signed_out" | "authenticated";

type Message = {
  role: "learner" | "tutor";
  text: string;
  meta?: string;
};

type SignupForm = {
  name: string;
  email: string;
  password: string;
  goal: string;
  initialTopic: string;
};

type LoginForm = {
  email: string;
  password: string;
};

const LOCAL_KEYS = {
  sessionPrefix: "adaptive-tutor.current-session"
} as const;

const DEFAULT_SIGNUP_FORM: SignupForm = {
  name: "",
  email: "",
  password: "",
  goal: "Learn algebra deeply",
  initialTopic: "algebra"
};

const DEFAULT_LOGIN_FORM: LoginForm = {
  email: "",
  password: ""
};

function safeStorageGet(key: string) {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(key);
}

function safeStorageSet(key: string, value: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(key, value);
}

function safeStorageRemove(key: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(key);
}

function sessionStorageKey(learnerId: string) {
  return `${LOCAL_KEYS.sessionPrefix}:${learnerId}`;
}

function getWeakestObjective(progressItem?: TopicProgress): ObjectiveProgress | null {
  if (!progressItem || progressItem.objectives.length === 0) {
    return null;
  }

  return [...progressItem.objectives].sort((left, right) => left.mastery - right.mastery)[0];
}

function getDefaultTopic(learner: Learner, preferredTopic?: string) {
  if (preferredTopic && preferredTopic.trim()) {
    return preferredTopic.trim();
  }

  const practicedTopics = Object.keys(learner.skills);
  if (practicedTopics.length > 0) {
    return practicedTopics[0];
  }

  return "algebra";
}

function formatDueLabel(isoDate: string) {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return "Soon";
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric"
  });
}

function authErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export function LearnerHome() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>("loading");
  const [authMode, setAuthMode] = useState<AuthMode>("signup");
  const [account, setAccount] = useState<Account | null>(null);
  const [learner, setLearner] = useState<Learner | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [progress, setProgress] = useState<TopicProgress[]>([]);
  const [lessonPlan, setLessonPlan] = useState<LessonPlan | null>(null);
  const [recommendations, setRecommendations] = useState<Concept[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [materials, setMaterials] = useState<SupplementalMaterial[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [signupForm, setSignupForm] = useState<SignupForm>(DEFAULT_SIGNUP_FORM);
  const [loginForm, setLoginForm] = useState<LoginForm>(DEFAULT_LOGIN_FORM);
  const [status, setStatus] = useState("Loading your study home...");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const currentTopic = session?.topic ?? (learner ? getDefaultTopic(learner) : "algebra");
  const currentProgress = useMemo(
    () => progress.find((item) => item.concept.slug === currentTopic),
    [progress, currentTopic]
  );
  const focusObjective = useMemo(() => getWeakestObjective(currentProgress), [currentProgress]);
  const nextRecommendation = useMemo(
    () => recommendations.find((item) => item.slug !== currentTopic) ?? recommendations[0] ?? null,
    [recommendations, currentTopic]
  );
  const currentMastery = currentProgress ? Math.round(currentProgress.concept_mastery * 100) : 0;
  const currentLessonStep = useMemo(() => {
    if (!lessonPlan) {
      return null;
    }
    return lessonPlan.steps[lessonPlan.current_step_index] ?? lessonPlan.steps[0] ?? null;
  }, [lessonPlan]);

  async function refreshPanels(nextLearner: Learner, nextTopic: string) {
    const [nextProgress, nextReviews, nextMaterials, nextRecommendations, nextLessonPlan] = await Promise.all([
      getProgress(nextLearner.id).catch(() => []),
      getDueReviews(nextLearner.id).catch(() => []),
      getMaterialSuggestions(nextLearner.id, nextTopic).catch(() => []),
      getCurriculumRecommendations(nextLearner.id).catch(() => []),
      getLessonPlan(nextLearner.id, nextTopic).catch(() => null)
    ]);

    setProgress(nextProgress);
    setReviews(nextReviews);
    setMaterials(nextMaterials);
    setRecommendations(nextRecommendations);
    setLessonPlan(nextLessonPlan);
  }

  function syncMessages(nextSession: Session, nextLearner: Learner) {
    if (nextSession.turns.length > 0) {
      setMessages(
        nextSession.turns.flatMap((turn) => [
          {
            role: "learner" as const,
            text: turn.learner_message
          },
          {
            role: "tutor" as const,
            text: turn.tutor_response,
            meta: `Tutor move: ${turn.tutor_action}`
          }
        ])
      );
      return;
    }

    setMessages([
      {
        role: "tutor",
        text: `Welcome back, ${nextLearner.name}. Let's continue with ${nextSession.topic}.`
      }
    ]);
  }

  async function ensureSession(nextLearner: Learner, preferredTopic?: string) {
    const storageKey = sessionStorageKey(nextLearner.id);
    const storedSessionId = safeStorageGet(storageKey);
    const fallbackTopic = getDefaultTopic(nextLearner, preferredTopic);

    let activeSession = storedSessionId ? await getSession(storedSessionId).catch(() => null) : null;
    if (!activeSession || activeSession.learner_id !== nextLearner.id) {
      activeSession = await createSession({
        learner_id: nextLearner.id,
        topic: fallbackTopic,
        mode: "learn"
      });
      safeStorageSet(storageKey, activeSession.id);
    }

    return activeSession;
  }

  async function loadAuthenticatedHome(authPayload: AuthPayload, preferredTopic?: string) {
    const activeSession = await ensureSession(authPayload.learner, preferredTopic);

    setAccount(authPayload.account);
    setLearner(authPayload.learner);
    setSession(activeSession);
    syncMessages(activeSession, authPayload.learner);
    await refreshPanels(authPayload.learner, activeSession.topic);
    setAuthStatus("authenticated");
    setStatus("Ready when you are.");
  }

  useEffect(() => {
    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          const currentAuth = await getCurrentAuth();
          if (!currentAuth) {
            setAuthStatus("signed_out");
            setStatus("Create your account to start learning.");
            return;
          }

          await loadAuthenticatedHome(currentAuth);
        } catch (loadError) {
          clearAuthSession();
          setAuthStatus("signed_out");
          setStatus("Sign in to continue.");
          setError(authErrorMessage(loadError, "Unable to load your account."));
        }
      })();
    });
  }, []);

  function handleSignup() {
    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          setStatus("Creating your study space...");
          const authPayload = await signup({
            email: signupForm.email.trim(),
            password: signupForm.password,
            name: signupForm.name.trim(),
            goal: signupForm.goal.trim(),
            initial_topic: signupForm.initialTopic.trim() || undefined
          });
          setAuthToken(authPayload.token);
          await loadAuthenticatedHome(authPayload, signupForm.initialTopic);
        } catch (signupError) {
          setError(authErrorMessage(signupError, "Unable to create your account."));
          setStatus("Create your account to start learning.");
        }
      })();
    });
  }

  function handleLogin() {
    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          setStatus("Signing you in...");
          const authPayload = await login({
            email: loginForm.email.trim(),
            password: loginForm.password
          });
          setAuthToken(authPayload.token);
          await loadAuthenticatedHome(authPayload);
        } catch (loginError) {
          setError(authErrorMessage(loginError, "Unable to sign in."));
          setStatus("Sign in to continue.");
        }
      })();
    });
  }

  function handleLogout() {
    startTransition(() => {
      void (async () => {
        try {
          await logout().catch(() => null);
        } finally {
          if (learner) {
            safeStorageRemove(sessionStorageKey(learner.id));
          }
          clearAuthSession();
          setAccount(null);
          setLearner(null);
          setSession(null);
          setProgress([]);
          setLessonPlan(null);
          setReviews([]);
          setMaterials([]);
          setMessages([]);
          setDraft("");
          setError(null);
          setAuthStatus("signed_out");
          setStatus("Signed out.");
        }
      })();
    });
  }

  function handleSend() {
    if (!learner || !session || !draft.trim()) {
      return;
    }

    const learnerMessage = draft.trim();
    setDraft("");
    setMessages((current) => [...current, { role: "learner", text: learnerMessage }]);

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          const response = await submitTurn(session.id, { message: learnerMessage, mode: session.mode });
          setLearner(response.updated_learner);
          setSession(response.updated_session);
          safeStorageSet(sessionStorageKey(response.updated_learner.id), response.updated_session.id);
          setMessages((current) => [
            ...current,
            {
              role: "tutor",
              text: response.tutor_response,
              meta: `Tutor move: ${response.tutor_action} | Current step: ${
                response.active_lesson_step?.title ?? "Adapting the lesson"
              } | Focus: ${response.evaluation.objective_id ?? "general understanding"}`
            }
          ]);
          setStatus(
            response.updated_session.topic === currentTopic
              ? "Nice progress."
              : `You advanced to ${response.updated_session.topic}.`
          );
          await refreshPanels(response.updated_learner, response.updated_session.topic);
        } catch (turnError) {
          setError(authErrorMessage(turnError, "Unable to continue the lesson."));
        }
      })();
    });
  }

function handleReview(reviewId: string) {
    if (!learner || !session) {
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          await completeReview(reviewId, true);
          await refreshPanels(learner, session.topic);
          setStatus("Review recorded.");
        } catch (reviewError) {
          setError(authErrorMessage(reviewError, "Unable to complete that review."));
        }
      })();
    });
  }

  function describeStepType(step: LessonPlanStep | null) {
    if (!step) {
      return "We’ll adapt the lesson structure once the tutor has more context.";
    }

    const labels: Record<LessonPlanStep["step_type"], string> = {
      explain: "Build understanding",
      diagnostic: "Check understanding",
      practice: "Practice actively",
      review: "Revisit a weak spot",
      advance: "Connect to the next idea"
    };

    return labels[step.step_type];
  }

  function getStepState(step: LessonPlanStep, index: number) {
    if (!lessonPlan) {
      return "upcoming";
    }
    if (lessonPlan.completed_step_ids.includes(step.id)) {
      return "completed";
    }
    if (index === lessonPlan.current_step_index) {
      return "active";
    }
    return index < lessonPlan.current_step_index ? "completed" : "upcoming";
  }

  function handleStartRecommendation(topicSlug: string) {
    if (!learner) {
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          const nextSession = await createSession({
            learner_id: learner.id,
            topic: topicSlug,
            mode: "learn"
          });
          setSession(nextSession);
          safeStorageSet(sessionStorageKey(learner.id), nextSession.id);
          syncMessages(nextSession, learner);
          await refreshPanels(learner, nextSession.topic);
          setStatus(`Starting ${topicSlug}.`);
        } catch (sessionError) {
          setError(authErrorMessage(sessionError, "Unable to start that lesson."));
        }
      })();
    });
  }

  if (authStatus === "loading") {
    return (
      <main className="landing-shell">
        <section className="loading-card">
          <p className="section-label">Adaptive Tutor</p>
          <h1>Loading your study home...</h1>
          <p className="supporting-text">Checking for an active session and bringing your learning state back in.</p>
        </section>
      </main>
    );
  }

  if (authStatus === "signed_out") {
    return (
      <main className="landing-shell">
        <header className="marketing-header">
          <div>
            <p className="topbar-eyebrow">Adaptive Tutor</p>
            <h1>Learn with a tutor that remembers how you learn.</h1>
          </div>
          <div className="topbar-actions">
            <button className="ghost-button" onClick={() => setAuthMode("login")}>
              Log in
            </button>
            <button className="primary-button" onClick={() => setAuthMode("signup")}>
              Sign up
            </button>
          </div>
        </header>

        <section className="landing-grid">
          <article className="panel landing-hero">
            <p className="section-label">Personalized Study</p>
            <h2>One place to continue learning, review weak spots, and ask for help.</h2>
            <p className="supporting-text">
              Adaptive Tutor keeps track of your progress, notices what still feels shaky, and adjusts how it teaches
              you over time.
            </p>

            <div className="feature-grid">
              <div className="info-tile">
                <strong>Adaptive lessons</strong>
                <p className="supporting-text">The tutor changes pace, explanation style, and next steps based on your answers.</p>
              </div>
              <div className="info-tile">
                <strong>Review built in</strong>
                <p className="supporting-text">Weak areas come back at the right time instead of getting lost after one session.</p>
              </div>
              <div className="info-tile">
                <strong>Visible progress</strong>
                <p className="supporting-text">See where you are strong, what still needs practice, and what comes next.</p>
              </div>
            </div>

            <div className="landing-actions">
              <button className="primary-button" onClick={() => setAuthMode("signup")}>
                Sign up to start learning
              </button>
              <button className="ghost-button" onClick={() => setAuthMode("login")}>
                I already have an account
              </button>
            </div>
          </article>

          <aside className="panel auth-panel">
            <div className="auth-tabs">
              <button
                className={`tab-button ${authMode === "signup" ? "active" : ""}`}
                onClick={() => setAuthMode("signup")}
              >
                Create account
              </button>
              <button
                className={`tab-button ${authMode === "login" ? "active" : ""}`}
                onClick={() => setAuthMode("login")}
              >
                Log in
              </button>
            </div>

            {authMode === "signup" ? (
              <div className="auth-stack">
                <div>
                  <p className="section-label">Get Started</p>
                  <h3>Create your learner account</h3>
                  <p className="supporting-text">We’ll use your goal and starting topic to open your first study session.</p>
                </div>

                <input
                  placeholder="Your name"
                  value={signupForm.name}
                  onChange={(event) => setSignupForm((current) => ({ ...current, name: event.target.value }))}
                />
                <input
                  placeholder="Email"
                  type="email"
                  value={signupForm.email}
                  onChange={(event) => setSignupForm((current) => ({ ...current, email: event.target.value }))}
                />
                <input
                  placeholder="Password"
                  type="password"
                  value={signupForm.password}
                  onChange={(event) => setSignupForm((current) => ({ ...current, password: event.target.value }))}
                />
                <input
                  placeholder="What do you want to learn?"
                  value={signupForm.goal}
                  onChange={(event) => setSignupForm((current) => ({ ...current, goal: event.target.value }))}
                />
                <input
                  placeholder="Starting topic"
                  value={signupForm.initialTopic}
                  onChange={(event) => setSignupForm((current) => ({ ...current, initialTopic: event.target.value }))}
                />
                <button
                  className="primary-button"
                  onClick={handleSignup}
                  disabled={
                    isPending ||
                    !signupForm.name.trim() ||
                    !signupForm.email.trim() ||
                    !signupForm.password ||
                    !signupForm.goal.trim()
                  }
                >
                  Sign up
                </button>
              </div>
            ) : (
              <div className="auth-stack">
                <div>
                  <p className="section-label">Welcome Back</p>
                  <h3>Log in to continue learning</h3>
                  <p className="supporting-text">Pick up right where you left off.</p>
                </div>

                <input
                  placeholder="Email"
                  type="email"
                  value={loginForm.email}
                  onChange={(event) => setLoginForm((current) => ({ ...current, email: event.target.value }))}
                />
                <input
                  placeholder="Password"
                  type="password"
                  value={loginForm.password}
                  onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
                />
                <button
                  className="primary-button"
                  onClick={handleLogin}
                  disabled={isPending || !loginForm.email.trim() || !loginForm.password}
                >
                  Log in
                </button>
              </div>
            )}

            <p className="supporting-text compact-text">{status}</p>
            {error ? <p className="error-text">{error}</p> : null}
          </aside>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="topbar-eyebrow">Adaptive Tutor</p>
          <h1>Welcome back{learner ? `, ${learner.name}` : ""}.</h1>
        </div>
        <div className="topbar-actions">
          <span className="status-chip">{status}</span>
          <Link className="text-link" href="/admin">
            Internal tools
          </Link>
          <button className="ghost-button" onClick={handleLogout} disabled={isPending}>
            Sign out
          </button>
        </div>
      </header>

      <section className="hero-card">
        <div>
          <p className="section-label">Current Goal</p>
          <h2>{learner?.goal ?? "Keep learning"}</h2>
          <p className="supporting-text">
            Your study home should tell you what matters right now, then help you continue without extra setup.
          </p>
        </div>
        <div className="hero-metrics">
          <article className="metric-card">
            <span>Today&apos;s focus</span>
            <strong>{session?.topic ?? "Choose a topic"}</strong>
          </article>
          <article className="metric-card">
            <span>Needs practice</span>
            <strong>{focusObjective?.objective.title ?? "Building foundations"}</strong>
          </article>
          <article className="metric-card">
            <span>Current mastery</span>
            <strong>{currentMastery}%</strong>
          </article>
        </div>
      </section>

      <section className="learner-grid">
        <div className="main-column">
          <article className="panel">
            <div className="section-header">
              <div>
                <p className="section-label">Continue Learning</p>
                <h3>{session?.topic ?? "Start your next lesson"}</h3>
              </div>
              <span className={`badge ${currentProgress?.ready_to_advance ? "ready" : "active"}`}>
                {currentProgress?.ready_to_advance ? "Ready to move on" : "Keep practicing"}
              </span>
            </div>
            <p className="supporting-text">
              {focusObjective
                ? `Right now the tutor is watching ${focusObjective.objective.title.toLowerCase()} most closely.`
                : "The tutor will adapt once you begin answering questions."}
            </p>
            <div className="study-plan">
              <div className="study-step">
                <span className="mini-tag">Now</span>
                <p className="supporting-text compact-text">Continue working in {session?.topic ?? "your current lesson"}.</p>
              </div>
              <div className="study-step">
                <span className="mini-tag">Focus</span>
                <p className="supporting-text compact-text">
                  {focusObjective
                    ? `${focusObjective.objective.title} is the weakest objective on this concept.`
                    : "The tutor will identify a focus area after a few turns."}
                </p>
              </div>
              <div className="study-step">
                <span className="mini-tag">Next</span>
                <p className="supporting-text compact-text">
                  {nextRecommendation
                    ? `${nextRecommendation.title} is the most likely next concept in your path.`
                    : "As you build momentum, the next recommended concept will show up here."}
                </p>
              </div>
            </div>
          </article>

          <article className="panel">
            <div className="section-header">
              <div>
                <p className="section-label">Lesson Plan</p>
                <h3>{lessonPlan?.summary ?? "Your tutor is building a plan for this topic."}</h3>
              </div>
              <span className="badge active">{describeStepType(currentLessonStep)}</span>
            </div>
            {currentLessonStep ? (
              <div className="plan-highlight">
                <strong>{currentLessonStep.title}</strong>
                <p className="supporting-text compact-text">{currentLessonStep.instruction}</p>
                <p className="supporting-text compact-text">{currentLessonStep.rationale}</p>
              </div>
            ) : null}
            <div className="lesson-plan-list">
              {lessonPlan?.steps.map((step, index) => {
                const stepState = getStepState(step, index);
                return (
                  <div key={step.id} className={`plan-step ${stepState}`}>
                    <div className="objective-title-row">
                      <strong>
                        {index + 1}. {step.title}
                      </strong>
                      <span className={`mini-tag ${stepState === "active" ? "active-tag" : stepState === "completed" ? "completed-tag" : ""}`}>
                        {stepState === "completed" ? "done" : stepState === "active" ? "active" : step.step_type}
                      </span>
                    </div>
                    <p className="supporting-text compact-text">{step.instruction}</p>
                  </div>
                );
              })}
            </div>
            {lessonPlan?.trace ? (
              <p className="supporting-text compact-text">
                Planned with {lessonPlan.trace.provider} using {lessonPlan.trace.model}.
              </p>
            ) : null}
          </article>

          <article className="panel lesson-panel">
            <div className="panel-heading">
              <div>
                <p className="section-label">Lesson</p>
                <h3>Work through the idea with your tutor</h3>
              </div>
            </div>

            <div className="message-stream">
              {messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                  <span className="message-tag">{message.role === "tutor" ? "Tutor" : "You"}</span>
                  <p>{message.text}</p>
                  {message.meta ? <p className="supporting-text compact-text">{message.meta}</p> : null}
                </div>
              ))}
            </div>

            <div className="composer-card">
              <textarea
                rows={4}
                placeholder="Answer the tutor, ask for another explanation, or say what feels confusing."
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
              <div className="composer-actions">
                {error ? <p className="error-text">{error}</p> : <p className="supporting-text compact-text">{status}</p>}
                <button className="primary-button" onClick={handleSend} disabled={isPending || !draft.trim()}>
                  Send
                </button>
              </div>
            </div>
          </article>
        </div>

        <aside className="side-column">
          <article className="panel">
            <div className="section-header">
              <div>
                <p className="section-label">What Comes Next</p>
                <h3>Your learning path</h3>
              </div>
            </div>
            {nextRecommendation ? (
              <div className="info-tile">
                <div className="objective-title-row">
                  <strong>{nextRecommendation.title}</strong>
                  <span className="mini-tag">{nextRecommendation.subject}</span>
                </div>
                <p className="supporting-text compact-text">{nextRecommendation.description}</p>
                <p className="supporting-text compact-text">
                  {currentProgress?.ready_to_advance
                    ? "You look ready to branch into this next concept."
                    : "This is the next likely stop once the current concept feels solid."}
                </p>
                <button
                  className="ghost-button inline-button"
                  onClick={() => handleStartRecommendation(nextRecommendation.slug)}
                  disabled={isPending}
                >
                  Start this lesson
                </button>
              </div>
            ) : (
              <div className="empty-card">
                <strong>We&apos;re still building your path.</strong>
                <p className="supporting-text compact-text">
                  Once we have enough context, the next recommended concept will appear here.
                </p>
              </div>
            )}
          </article>

          <article className="panel">
            <div className="section-header">
              <div>
                <p className="section-label">Today</p>
                <h3>Review queue</h3>
              </div>
            </div>
            <div className="stack-list">
              {reviews.length > 0 ? (
                reviews.map((review) => (
                  <div key={review.id} className="info-tile">
                    <strong>{review.topic}</strong>
                    <p className="supporting-text compact-text">Due {formatDueLabel(review.due_at)}</p>
                    <p className="supporting-text compact-text">{review.review_count} prior review{review.review_count === 1 ? "" : "s"}</p>
                    <button className="ghost-button inline-button" onClick={() => handleReview(review.id)} disabled={isPending}>
                      Mark reviewed
                    </button>
                  </div>
                ))
              ) : (
                <div className="empty-card">
                  <strong>No reviews due right now.</strong>
                  <p className="supporting-text compact-text">New review work will appear here as the tutor tracks weaker areas.</p>
                </div>
              )}
            </div>
          </article>

          <article className="panel">
            <div className="section-header">
              <div>
                <p className="section-label">Lesson Sources</p>
                <h3>What today&apos;s lesson is drawing from</h3>
              </div>
            </div>
            <div className="stack-list">
              {materials.length > 0 ? (
                materials.map((material) => (
                  <div key={material.id} className="info-tile">
                    <div className="objective-title-row">
                      <strong>{material.title}</strong>
                      <span className="mini-tag">{material.material_type}</span>
                    </div>
                    <p className="supporting-text compact-text">{material.description}</p>
                    <p className="supporting-text compact-text">{material.rationale}</p>
                    <p className="supporting-text compact-text">Source cue: {material.query}</p>
                  </div>
                ))
              ) : (
                <div className="empty-card">
                  <strong>No lesson sources yet.</strong>
                  <p className="supporting-text compact-text">As we learn more about your weak spots, we&apos;ll recommend targeted material here.</p>
                </div>
              )}
            </div>
          </article>
        </aside>
      </section>

      <section className="progress-section">
        <div className="section-header">
          <div>
            <p className="section-label">Progress</p>
            <h3>How your current track is shaping up</h3>
          </div>
          <p className="supporting-text compact-text">{account?.email}</p>
        </div>

        <div className="progress-grid">
          {progress.length > 0 ? (
            progress.map((item) => (
              <article key={item.concept.id} className="panel progress-panel">
                <header>
                  <div>
                    <strong>{item.concept.title}</strong>
                    <p className="supporting-text compact-text">{item.concept.description}</p>
                  </div>
                  <span className={`badge ${item.ready_to_advance ? "ready" : "active"}`}>
                    {item.ready_to_advance ? "Ready" : "In progress"}
                  </span>
                </header>
                <div className="objective-list">
                  {item.objectives.map((objective) => (
                    <div key={objective.objective.id} className="objective-item">
                      <div className="objective-title-row">
                        <strong>{objective.objective.title}</strong>
                        <span className="mini-tag">{Math.round(objective.mastery * 100)}%</span>
                      </div>
                      <div className="meter">
                        <span style={{ width: `${Math.round(objective.mastery * 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </article>
            ))
          ) : (
            <article className="panel empty-card">
              <strong>Your detailed progress will appear here as you study.</strong>
              <p className="supporting-text compact-text">
                Start a lesson and the tutor will begin tracking how each objective is developing.
              </p>
            </article>
          )}
        </div>
      </section>
    </main>
  );
}
