"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useTransition } from "react";
import {
  clearAuthSession,
  completeReview,
  createStudySession,
  getCurrentAuth,
  getDueReviews,
  getLessonPlan,
  getLessonWorkspace,
  getLatestSession,
  getProgress,
  getSession,
  login,
  logout,
  setAuthToken,
  signup,
  submitCheckpointAttempt,
  submitTurn
} from "@/lib/api";
import type {
  Account,
  AuthPayload,
  CheckpointAttemptResponse,
  Learner,
  LessonContentBlock,
  LessonWorkspace,
  LessonPlan,
  LessonPlanStep,
  ObjectiveProgress,
  ReviewItem,
  Session,
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
  const [workspace, setWorkspace] = useState<LessonWorkspace | null>(null);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [reviewAnswers, setReviewAnswers] = useState<Record<string, string>>({});
  const [checkpointSelections, setCheckpointSelections] = useState<Record<string, string>>({});
  const [checkpointResults, setCheckpointResults] = useState<Record<string, CheckpointAttemptResponse>>({});
  const [studyIntent, setStudyIntent] = useState("");
  const [draft, setDraft] = useState("");
  const [signupForm, setSignupForm] = useState<SignupForm>(DEFAULT_SIGNUP_FORM);
  const [loginForm, setLoginForm] = useState<LoginForm>(DEFAULT_LOGIN_FORM);
  const [status, setStatus] = useState("Loading your study home...");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const currentTopic = session?.topic ?? "";
  const currentProgress = useMemo(
    () => progress.find((item) => item.concept.slug === currentTopic),
    [progress, currentTopic]
  );
  const focusObjective = useMemo(() => getWeakestObjective(currentProgress), [currentProgress]);
  const currentMastery = currentProgress ? Math.round(currentProgress.concept_mastery * 100) : 0;
  const currentLessonStep = useMemo(() => {
    if (!lessonPlan) {
      return null;
    }
    return lessonPlan.steps[lessonPlan.current_step_index] ?? lessonPlan.steps[0] ?? null;
  }, [lessonPlan]);

  async function refreshWorkspace(learnerId: string) {
    const nextWorkspace = await getLessonWorkspace(learnerId).catch(() => null);
    setWorkspace(nextWorkspace);
    if (nextWorkspace) {
      setLessonPlan(nextWorkspace.lesson_plan);
      setSession(nextWorkspace.session);
    }
    return nextWorkspace;
  }

  async function refreshPanels(nextLearner: Learner, nextTopic: string) {
    setError(null);
    const [nextProgressResult, nextReviewsResult, nextLessonPlanResult, nextWorkspaceResult] = await Promise.allSettled([
      getProgress(nextLearner.id),
      getDueReviews(nextLearner.id),
      getLessonPlan(nextLearner.id, nextTopic),
      getLessonWorkspace(nextLearner.id),
    ]);

    const nextProgress = nextProgressResult.status === "fulfilled" ? nextProgressResult.value : [];
    const nextReviews = nextReviewsResult.status === "fulfilled" ? nextReviewsResult.value : [];
    const nextLessonPlan = nextLessonPlanResult.status === "fulfilled" ? nextLessonPlanResult.value : null;
    const nextWorkspace = nextWorkspaceResult.status === "fulfilled" ? nextWorkspaceResult.value : null;

    setProgress(nextProgress);
    setReviews(nextReviews);
    setLessonPlan(nextWorkspace?.lesson_plan ?? nextLessonPlan);
    setWorkspace(nextWorkspace);
    if (nextWorkspace) {
      setSession(nextWorkspace.session);
    }

    const failures = [
      nextProgressResult.status === "rejected" ? "progress" : null,
      nextReviewsResult.status === "rejected" ? "reviews" : null,
      nextLessonPlanResult.status === "rejected" ? "lesson plan" : null,
      nextWorkspaceResult.status === "rejected" ? "lesson workspace" : null
    ].filter(Boolean);

    if (failures.length > 0) {
      const label = failures.join(", ");
      setError(`Some parts of your study home failed to load: ${label}. Check the API logs for details.`);
      setStatus("Some study panels did not load cleanly.");
    } else {
      setError(null);
    }
  }

  function syncMessages(nextSession: Session, nextLearner: Learner, nextLessonPlan?: LessonPlan | null) {
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

    const kickoff = nextLessonPlan?.steps[nextLessonPlan.current_step_index] ?? nextLessonPlan?.steps[0] ?? null;
    setMessages([
      {
        role: "tutor",
        text: kickoff
          ? `Welcome back, ${nextLearner.name}. We’re starting with ${kickoff.title.toLowerCase()} in ${nextSession.topic}. ${kickoff.instruction}`
          : `Welcome back, ${nextLearner.name}. Let's continue with ${nextSession.topic}. Tell me what already makes sense and what feels fuzzy.`
      }
    ]);
  }

  async function loadStoredSession(nextLearner: Learner) {
    const storageKey = sessionStorageKey(nextLearner.id);
    const storedSessionId = safeStorageGet(storageKey);
    const storedSession = storedSessionId ? await getSession(storedSessionId).catch(() => null) : null;
    if (storedSession && storedSession.learner_id === nextLearner.id) {
      return storedSession;
    }

    const latestSession = await getLatestSession(nextLearner.id);
    if (latestSession) {
      safeStorageSet(storageKey, latestSession.id);
    }
    return latestSession;
  }

  async function loadAuthenticatedHome(authPayload: AuthPayload) {
    setAccount(authPayload.account);
    setLearner(authPayload.learner);
    const activeSession = await loadStoredSession(authPayload.learner);
    if (activeSession) {
      const activeWorkspace = await refreshWorkspace(authPayload.learner.id);
      const activeLessonPlan = activeWorkspace?.lesson_plan ?? await getLessonPlan(authPayload.learner.id, activeSession.topic).catch(() => null);
      setSession(activeWorkspace?.session ?? activeSession);
      syncMessages(activeWorkspace?.session ?? activeSession, authPayload.learner, activeLessonPlan);
      setLessonPlan(activeLessonPlan);
      await refreshPanels(authPayload.learner, activeSession.topic);
      setStatus("Ready when you are.");
    } else {
      setSession(null);
      setLessonPlan(null);
      setWorkspace(null);
      setMessages([]);
      setProgress([]);
      setReviews([]);
      setStatus("What do you want to learn today?");
    }
    setAuthStatus("authenticated");
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
            name: signupForm.name.trim()
          });
          setAuthToken(authPayload.token);
          await loadAuthenticatedHome(authPayload);
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
          setWorkspace(null);
          setReviews([]);
          setMessages([]);
          setReviewAnswers({});
          setCheckpointSelections({});
          setCheckpointResults({});
          setStudyIntent("");
          setDraft("");
          setError(null);
          setAuthStatus("signed_out");
          setStatus("Signed out.");
        }
      })();
    });
  }

  function submitLearnerMessage(learnerMessage: string) {
    if (!learner || !session || !learnerMessage.trim()) {
      return;
    }
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
          setCheckpointSelections({});
          setCheckpointResults({});
        } catch (turnError) {
          setError(authErrorMessage(turnError, "Unable to continue the lesson."));
        }
      })();
    });
  }

  function handleSend() {
    if (!draft.trim()) {
      return;
    }
    submitLearnerMessage(draft.trim());
  }

  function handleQuickPrompt(message: string) {
    setDraft(message);
  }

  function handleQuickStart(message: string) {
    submitLearnerMessage(message);
  }

  function handleReview(reviewId: string) {
    if (!learner || !session) {
      return;
    }
    const answer = reviewAnswers[reviewId]?.trim();
    if (!answer) {
      setError("Write a short answer before submitting the review.");
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          await completeReview(reviewId, answer);
          setReviewAnswers((current) => {
            const next = { ...current };
            delete next[reviewId];
            return next;
          });
          await refreshPanels(learner, session.topic);
          setStatus("Review recorded.");
        } catch (reviewError) {
          setError(authErrorMessage(reviewError, "Unable to complete that review."));
        }
      })();
    });
  }

  function handleCheckpointSubmit(checkpointId: string) {
    if (!learner) {
      return;
    }
    const selectedOptionId = checkpointSelections[checkpointId];
    if (!selectedOptionId) {
      setError("Choose an answer before submitting the checkpoint.");
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          const result = await submitCheckpointAttempt(learner.id, checkpointId, selectedOptionId);
          setCheckpointResults((current) => ({ ...current, [checkpointId]: result }));
          setLearner(result.updated_learner);
          await refreshPanels(result.updated_learner, currentTopic);
          setStatus(result.is_correct ? "Checkpoint complete." : "Let's reinforce that idea.");
        } catch (checkpointError) {
          setError(authErrorMessage(checkpointError, "Unable to submit that checkpoint."));
        }
      })();
    });
  }

  function renderLessonBlock(block: LessonContentBlock) {
    if (block.type === "heading" && block.text) {
      return <h4 className="lesson-block-heading">{block.text}</h4>;
    }
    if (block.type === "paragraph" && block.text) {
      return <p className="lesson-block-text">{block.text}</p>;
    }
    if (block.type === "example" && block.text) {
      return (
        <div className="lesson-example">
          <strong>Example</strong>
          <p className="lesson-block-text">{block.text}</p>
        </div>
      );
    }
    if (block.type === "summary" && block.text) {
      return (
        <div className="lesson-summary">
          <strong>Summary</strong>
          <p className="lesson-block-text">{block.text}</p>
        </div>
      );
    }
    if (block.type === "go_deeper") {
      return (
        <div className="lesson-go-deeper">
          <span className="mini-tag">Go deeper</span>
          <div className="lesson-actions">
            {block.prompts.map((prompt) => (
              <button
                key={prompt}
                className="ghost-button"
                onClick={() => handleQuickStart(prompt)}
                disabled={isPending || !session}
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      );
    }
    if (block.type === "checkpoint_mcq" && block.checkpoint) {
      const result = checkpointResults[block.checkpoint.id];
      const selected = checkpointSelections[block.checkpoint.id];
      return (
        <div className="lesson-checkpoint">
          <span className="mini-tag">Quick check</span>
          <strong>{block.checkpoint.prompt}</strong>
          <div className="checkpoint-options">
            {block.checkpoint.options.map((option) => (
              <button
                key={option.id}
                className={`checkpoint-option ${selected === option.id ? "selected" : ""}`}
                onClick={() =>
                  setCheckpointSelections((current) => ({ ...current, [block.checkpoint!.id]: option.id }))
                }
                disabled={isPending || Boolean(result)}
              >
                <span>{option.label}</span>
                <span>{option.text}</span>
              </button>
            ))}
          </div>
          {result ? (
            <div className={`checkpoint-feedback ${result.is_correct ? "correct" : "incorrect"}`}>
              <strong>{result.is_correct ? "Correct" : "Not quite"}</strong>
              <p className="lesson-block-text">{result.explanation}</p>
            </div>
          ) : (
            <button
              className="primary-button"
              onClick={() => handleCheckpointSubmit(block.checkpoint!.id)}
              disabled={isPending || !selected}
            >
              Submit check
            </button>
          )}
        </div>
      );
    }
    return null;
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

  function handleStartStudyIntent(prefill?: string) {
    if (!learner) {
      return;
    }
    const prompt = (prefill ?? studyIntent).trim();
    if (!prompt) {
      setError("Tell the tutor what you want to learn today.");
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          setStatus("Building your lesson...");
          const response = await createStudySession(learner.id, {
            prompt,
            mode: "learn"
          });
          setLearner(response.learner);
          setSession(response.session);
          setLessonPlan(response.lesson_plan);
          await refreshWorkspace(response.learner.id);
          setStudyIntent("");
          safeStorageSet(sessionStorageKey(response.learner.id), response.session.id);
          syncMessages(response.session, response.learner, response.lesson_plan);
          await refreshPanels(response.learner, response.session.topic);
          setStatus(`Ready to learn ${response.concept.title}.`);
        } catch (studyError) {
          setError(authErrorMessage(studyError, "Unable to build your lesson right now."));
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
                  <p className="supporting-text">Create your account first. We&apos;ll ask what you want to learn after you sign in.</p>
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
                <button
                  className="primary-button"
                  onClick={handleSignup}
                  disabled={
                    isPending ||
                    !signupForm.name.trim() ||
                    !signupForm.email.trim() ||
                    !signupForm.password
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
          {account?.is_admin ? (
            <Link className="text-link" href="/admin">
              Internal tools
            </Link>
          ) : null}
          <button className="ghost-button" onClick={handleLogout} disabled={isPending}>
            Sign out
          </button>
        </div>
      </header>

      {!session ? (
        <section className="landing-grid">
          <article className="panel landing-hero">
            <p className="section-label">Start Today</p>
            <h2>What do you want to learn today?</h2>
            <p className="supporting-text">
              Tell the tutor what you want to work on in plain language. We&apos;ll generate the lesson plan, objectives,
              and first teaching step from that request.
            </p>
            <textarea
              rows={4}
              placeholder="Examples: Learn the basics of neural networks, understand Russian literature, prepare for a system design interview."
              value={studyIntent}
              onChange={(event) => setStudyIntent(event.target.value)}
            />
            <div className="landing-actions">
              <button
                className="primary-button"
                onClick={() => handleStartStudyIntent()}
                disabled={isPending || !studyIntent.trim()}
              >
                Build my lesson
              </button>
            </div>
            <div className="feature-grid">
              {[
                "Learn the basics of neural networks",
                "Understand Russian literature",
                "Practice system design interviews",
              ].map((example) => (
                <button
                  key={example}
                  className="info-tile"
                  onClick={() => setStudyIntent(example)}
                  disabled={isPending}
                >
                  <strong>{example}</strong>
                  <p className="supporting-text compact-text">Use this as today&apos;s study prompt.</p>
                </button>
              ))}
            </div>
          </article>

          <aside className="panel auth-panel">
            <div className="auth-stack">
              <div>
                <p className="section-label">How It Works</p>
                <h3>No preloaded course required</h3>
                <p className="supporting-text">
                  We generate today&apos;s curriculum after you tell us what you want to learn, then turn it into a live
                  tutoring session.
                </p>
              </div>
              <div className="info-tile">
                <strong>1. State your goal</strong>
                <p className="supporting-text compact-text">Use natural language instead of picking from a rigid catalog.</p>
              </div>
              <div className="info-tile">
                <strong>2. Get a lesson plan</strong>
                <p className="supporting-text compact-text">The tutor creates objectives, sequence, and a first step.</p>
              </div>
              <div className="info-tile">
                <strong>3. Start learning</strong>
                <p className="supporting-text compact-text">The conversation begins with a concrete first move, not a blank screen.</p>
              </div>
              <p className="supporting-text compact-text">{status}</p>
              {error ? <p className="error-text">{error}</p> : null}
            </div>
          </aside>
        </section>
      ) : (
      <>
      <section className="lesson-layout">
        <div className="main-column">
          <article className="panel lesson-panel lesson-panel-primary">
            <div className="panel-heading">
              <div>
                <p className="section-label">Lesson</p>
                <h3>{session?.topic ?? "Your lesson"}</h3>
                <p className="supporting-text compact-text">
                  {currentLessonStep
                    ? `Current step: ${currentLessonStep.title}. ${currentLessonStep.instruction}`
                    : "Start with a guided action below and the tutor will take the lead."}
                </p>
              </div>
              <span className={`badge ${currentProgress?.ready_to_advance ? "ready" : "active"}`}>
                {currentProgress?.ready_to_advance ? "Ready to move on" : "Keep practicing"}
              </span>
            </div>

            <div className="lesson-actions">
              <button
                className="primary-button"
                onClick={() =>
                  handleQuickStart(
                    currentLessonStep
                      ? `I'm ready. Start with "${currentLessonStep.title}" and guide me step by step.`
                      : `I'm ready to continue with ${session?.topic ?? "this lesson"}.`
                  )
                }
                disabled={isPending || !session}
              >
                Resume lesson
              </button>
              <button
                className="ghost-button"
                onClick={() =>
                  handleQuickStart(
                    focusObjective
                      ? `Explain ${focusObjective.objective.title.toLowerCase()} in a simpler way.`
                      : `Explain the core idea in ${session?.topic ?? "this topic"} more simply.`
                  )
                }
                disabled={isPending || !session}
              >
                Explain differently
              </button>
              <button
                className="ghost-button"
                onClick={() =>
                  handleQuickStart(
                    focusObjective
                      ? `Give me one short practice question on ${focusObjective.objective.title.toLowerCase()}.`
                      : `Give me one short practice question on ${session?.topic ?? "this topic"}.`
                  )
                }
                disabled={isPending || !session}
              >
                Practice now
              </button>
              <button
                className="ghost-button"
                onClick={() => {
                  if (learner) {
                    safeStorageRemove(sessionStorageKey(learner.id));
                  }
                  setSession(null);
                  setLessonPlan(null);
                  setMessages([]);
                  setProgress([]);
                  setReviews([]);
                  setDraft("");
                  setStatus("What do you want to learn today?");
                }}
                disabled={isPending}
              >
                Learn something else
              </button>
            </div>

            <div className="message-stream">
              {workspace?.section_content ? (
                <div className="lesson-content-card">
                  <div className="lesson-content-header">
                    <p className="section-label">Section</p>
                    <h4>{workspace.section_content.title}</h4>
                    {workspace.section_content.subtitle ? (
                      <p className="supporting-text compact-text">{workspace.section_content.subtitle}</p>
                    ) : null}
                  </div>
                  <div className="lesson-content-flow">
                    {workspace.section_content.blocks.map((block) => (
                      <div key={block.id}>{renderLessonBlock(block)}</div>
                    ))}
                  </div>
                </div>
              ) : null}
              {session?.turns.length === 0 ? (
                <div className="plan-highlight">
                  <strong>{currentLessonStep?.title ?? `Start learning ${session?.topic ?? ""}`}</strong>
                  <p className="supporting-text compact-text">
                    {currentLessonStep?.instruction ??
                      "Choose one of the guided starts below and the tutor will take the first step with you."}
                  </p>
                  <div className="landing-actions">
                    <button
                      className="primary-button"
                      onClick={() =>
                        handleQuickStart(
                          currentLessonStep
                            ? `Teach me ${currentLessonStep.title.toLowerCase()} from the beginning with one simple example.`
                            : `Teach me the core idea in ${session?.topic ?? "this topic"} from the beginning.`
                        )
                      }
                      disabled={isPending || !session}
                    >
                      Start guided lesson
                    </button>
                    <button
                      className="ghost-button"
                      onClick={() =>
                        handleQuickStart(
                          `Ask me one short diagnostic question about ${session?.topic ?? "this topic"} to find my level.`
                        )
                      }
                      disabled={isPending || !session}
                    >
                      Check my level
                    </button>
                    <button
                      className="ghost-button"
                      onClick={() =>
                        handleQuickStart(
                          `Give me a quick overview of ${session?.topic ?? "this topic"} and why it matters.`
                        )
                      }
                      disabled={isPending || !session}
                    >
                      Give overview
                    </button>
                  </div>
                </div>
              ) : null}
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
                <p className="section-label">Session Focus</p>
                <h3>What matters right now</h3>
              </div>
            </div>
            <div className="stack-list">
              <div className="info-tile">
                <strong>Focus area</strong>
                <p className="supporting-text compact-text">
                  {focusObjective
                    ? focusObjective.objective.title
                    : "The tutor will identify the main weak spot after a few turns."}
                </p>
              </div>
              <div className="info-tile">
                <strong>Current step</strong>
                <p className="supporting-text compact-text">
                  {currentLessonStep ? currentLessonStep.title : "Starting your lesson"}
                </p>
              </div>
              <div className="info-tile">
                <strong>Lesson summary</strong>
                <p className="supporting-text compact-text">
                  {lessonPlan?.summary ?? "A plan will appear as soon as the lesson is generated."}
                </p>
              </div>
            </div>
          </article>

          <article className="panel">
            <div className="section-header">
              <div>
                <p className="section-label">Roadmap</p>
                <h3>Your lesson plan</h3>
              </div>
            </div>
            <div className="lesson-plan-list compact-plan-list">
              {lessonPlan?.steps.map((step, index) => {
                const stepState = getStepState(step, index);
                return (
                  <div key={step.id} className={`plan-step ${stepState}`}>
                    <div className="objective-title-row">
                      <strong>{index + 1}. {step.title}</strong>
                      <span className={`mini-tag ${stepState === "active" ? "active-tag" : stepState === "completed" ? "completed-tag" : ""}`}>
                        {stepState === "completed" ? "done" : stepState === "active" ? "active" : step.step_type}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
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
                    <p className="supporting-text compact-text">{review.prompt}</p>
                    <p className="supporting-text compact-text">Due {formatDueLabel(review.due_at)}</p>
                    <p className="supporting-text compact-text">{review.review_count} prior review{review.review_count === 1 ? "" : "s"}</p>
                    <textarea
                      rows={3}
                      placeholder="Write your answer from memory."
                      value={reviewAnswers[review.id] ?? ""}
                      onChange={(event) =>
                        setReviewAnswers((current) => ({ ...current, [review.id]: event.target.value }))
                      }
                    />
                    <button className="ghost-button inline-button" onClick={() => handleReview(review.id)} disabled={isPending || !(reviewAnswers[review.id] ?? "").trim()}>
                      Submit review
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
      </>
      )}
    </main>
  );
}
