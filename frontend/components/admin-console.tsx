"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";
import { createConcept, getCurrentAuth } from "@/lib/api";

const starterCurriculum = [
  {
    slug: "algebra",
    title: "Algebra Foundations",
    description: "Core algebraic manipulation and symbolic reasoning.",
    subject: "math",
    prerequisites: []
  },
  {
    slug: "derivatives",
    title: "Derivatives",
    description: "Rates of change and how functions vary.",
    subject: "math",
    prerequisites: ["algebra"]
  },
  {
    slug: "russian-literature",
    title: "Russian Literature",
    description: "Themes, historical context, and close reading in Russian literature.",
    subject: "literature",
    prerequisites: []
  }
];

export function AdminConsole() {
  const [status, setStatus] = useState("Use this page for internal/demo setup only.");
  const [isAdmin, setIsAdmin] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    void (async () => {
      const auth = await getCurrentAuth();
      setIsAdmin(Boolean(auth?.account.is_admin));
      setIsLoading(false);
    })();
  }, []);

  function handleSeed() {
    startTransition(async () => {
      await Promise.all(
        starterCurriculum.map(async (concept) => {
          try {
            await createConcept({
              ...concept,
              prerequisites: [...concept.prerequisites]
            });
          } catch {
            return null;
          }
          return null;
        })
      );
      setStatus("Starter curriculum seeded or already present.");
    });
  }

  if (isLoading) {
    return (
      <main className="app-shell admin-shell">
        <section className="panel admin-card">
          <p className="section-label">Internal Route</p>
          <h2>Checking access…</h2>
        </section>
      </main>
    );
  }

  if (!isAdmin) {
    return (
      <main className="app-shell admin-shell">
        <section className="panel admin-card">
          <p className="section-label">Restricted</p>
          <h2>Admin access required</h2>
          <p className="supporting-text">
            This route is only available to internal admins and curriculum authors.
          </p>
          <Link className="text-link" href="/">
            Back to learner app
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell admin-shell">
      <header className="topbar">
        <div>
          <p className="topbar-eyebrow">Internal Route</p>
          <h1>Admin Tools</h1>
        </div>
        <Link className="text-link" href="/">
          Back to learner app
        </Link>
      </header>

      <section className="admin-grid">
        <article className="panel admin-card">
          <p className="section-label">Curriculum</p>
          <h2>Seed starter concepts</h2>
          <p className="supporting-text">
            This route is for setup and debugging. It should stay separate from the learner-facing experience.
          </p>
          <button className="primary-button" onClick={handleSeed} disabled={isPending}>
            Seed Starter Curriculum
          </button>
          <p className="supporting-text">{status}</p>
        </article>

        <article className="panel admin-card">
          <p className="section-label">Design Note</p>
          <h2>What belongs here</h2>
          <ul className="admin-list">
            <li>Seed data and curriculum setup</li>
            <li>Debug learner/session issues</li>
            <li>Internal feature toggles and authoring tools</li>
          </ul>
        </article>
      </section>
    </main>
  );
}
