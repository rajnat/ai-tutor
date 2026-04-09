# Adaptive Tutor

Adaptive Tutor is an AI-first learning system that turns a learner's study goal into a generated course, teaches through a live tutor, and updates its teaching strategy as the learner progresses.

The project is meant to explore a more structured alternative to “just a chatbot”: instead of responding turn by turn with no durable learning model, the system generates a course, persists lesson state, embeds checkpoints, tracks weak objectives, and uses that state to shape the next teaching move.

## Why This Project Is Interesting

Most AI tutoring demos stop at chat. This project pushes further into product and systems design:

- the learner starts with a natural-language study goal instead of selecting from a fixed curriculum
- the backend generates a scoped topic, objectives, lesson plan, and structured lesson section
- the frontend renders that as a course workspace rather than a generic chat UI
- the system persists course sections, checkpoint attempts, lesson plans, sessions, and learner progress
- the tutor loop combines planning, evaluation, course state, and learner-state updates instead of relying only on conversation history

That makes the system a better fit for real learning workflows, even though it is still early.

## Current Product Flow

1. A learner signs up or logs in.
2. If a prior lesson exists, the app resumes it.
3. Otherwise, the learner answers: `What do you want to learn today?`
4. The backend uses the LLM to:
   - infer a teachable topic
   - generate objectives
   - create a lesson plan
   - generate structured section content with checkpoints
5. The learner enters a course-style workspace with:
   - a section outline
   - a lesson reader
   - embedded MCQ checks
   - a tutor conversation thread
   - reviews and progress signals

## System Architecture

### Core Stack

- FastAPI backend
- SQLAlchemy + Alembic
- Next.js frontend
- PostgreSQL for local Docker development
- OpenAI-backed LLM services
- cookie-based auth with CSRF protection

### Backend Responsibilities

- `StudyIntentService`
  Turns a learner's request into a scoped topic and objective set.

- `LessonPlannerService`
  Generates a lesson sequence that can be rendered like a small course.

- `LessonContentService`
  Generates structured section content with checkpoint blocks.

- `CourseWorkspaceService`
  Persists course, section, section-content, and checkpoint-attempt state for the frontend.

- `SessionOrchestrator`
  Handles tutor turns, learner evaluation, action selection, and learner-model updates.

### Runtime Flow

```text
Learner request
  -> study-intent generation
  -> concept/objective creation
  -> lesson-plan generation
  -> persisted course + sections
  -> section-content generation
  -> learner interacts with lesson + tutor
  -> checkpoint/tutor responses update learner state
  -> course and lesson state advance
```

## What Is Implemented

### Learner Experience

- signed-out landing page plus authenticated learner workspace
- study-intent driven course creation
- resumable sessions
- section-based course navigation
- lesson-reader layout
- tutor conversation thread
- embedded multiple-choice checkpoints
- review prompts and progress summaries

### Backend Capabilities

- learner, session, lesson-plan, review, and course persistence
- course section activation
- checkpoint attempt persistence
- objective-level learner state tracking
- misconception tracking
- LLM-backed evaluation and teaching
- LLM-backed study-intent parsing, lesson planning, and section generation
- prompt/version trace capture on generated artifacts and turns

### Security / App Concerns

- account signup and login
- `HttpOnly` cookie sessions
- CSRF protection
- learner-scoped authorization
- admin-only curriculum mutation route

## Local Development

### Recommended: Docker Compose

Create a repo-root `.env`:

```env
OPENAI_API_KEY=sk-...
ADAPTIVE_TUTOR_LLM_PROVIDER=openai
ADAPTIVE_TUTOR_OPENAI_MODEL=gpt-5.4
ADAPTIVE_TUTOR_CORS_ALLOWED_ORIGINS=http://localhost:3001
ADAPTIVE_TUTOR_AUTH_COOKIE_SECURE=false
```

Start the stack:

```bash
docker-compose up --build
```

Local services:

- frontend: `http://localhost:3001`
- API: `http://localhost:8000`
- Postgres: `localhost:5433`

Stop the stack:

```bash
docker-compose down
```

Useful commands:

```bash
docker-compose logs -f api
docker-compose exec api uv run alembic upgrade head
docker-compose exec api uv run pytest
```

### Without Docker

Backend:

```bash
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## LLM Configuration

The product is currently LLM-first. Because there is not yet a full ingestion pipeline or grounded content library, the LLM is responsible for:

- parsing the learner's study goal
- planning the lesson
- generating section content
- generating tutor responses
- evaluating learner responses

Relevant environment variables:

- `ADAPTIVE_TUTOR_LLM_PROVIDER`
- `OPENAI_API_KEY`
- `ADAPTIVE_TUTOR_OPENAI_MODEL`
- `ADAPTIVE_TUTOR_OPENAI_BASE_URL`

Current provider modes:

- `openai`: live app behavior
- `stub`: deterministic test/dev behavior

## Auth and Security

Browser auth uses server-issued cookies:

- `HttpOnly` session cookie
- readable CSRF cookie
- `X-CSRF-Token` header on mutating requests
- `credentials: include` on frontend requests

Relevant settings:

- `ADAPTIVE_TUTOR_AUTH_COOKIE_NAME`
- `ADAPTIVE_TUTOR_AUTH_COOKIE_SECURE`
- `ADAPTIVE_TUTOR_CSRF_COOKIE_NAME`
- `ADAPTIVE_TUTOR_CSRF_HEADER_NAME`
- `ADAPTIVE_TUTOR_CORS_ALLOWED_ORIGINS`

## Database and Migrations

Alembic migrations live in [`migrations/versions`](/Users/eswar/Projects/ai-tutor/migrations/versions).

Common commands:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic revision -m "describe change"
```

Notes:

- migration scripts should be committed
- local `.db` files should not be committed
- `uv.lock` should be committed because this is an application

## API Surface

Main routes:

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/learners/{learner_id}/study-session`
- `GET /api/v1/learners/{learner_id}/sessions/latest`
- `GET /api/v1/learners/{learner_id}/workspace`
- `POST /api/v1/learners/{learner_id}/courses/{course_id}/sections/activate`
- `POST /api/v1/sessions/{session_id}/turns`
- `POST /api/v1/learners/{learner_id}/checkpoints/{checkpoint_id}/attempt`
- `GET /api/v1/learners/{learner_id}/reviews/due`
- `POST /api/v1/reviews/{review_id}/complete`
- `GET /api/v1/learners/{learner_id}/progress/objectives`
- `GET /api/v1/learners/{learner_id}/lesson-plan`
- `GET /api/v1/learners/{learner_id}/curriculum/recommendations`
- `GET /api/v1/learners/{learner_id}/materials/suggestions`
- `POST /api/v1/curriculum/concepts` (admin only)

## Current Gaps / Next Steps

This is an active prototype, not a finished product. The most important open problems are:

- prompt quality and consistency across subsystems
- stronger course grounding beyond pure LLM generation
- richer observability and analytics
- more polished review and study-guide experiences
- flashcards and stronger spaced repetition flows
- more explicit testing/exam modes

## Verification

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall app
uv run pytest -q
cd frontend && npm run build
```
