export type LearningPreferences = {
  verbosity: "low" | "medium" | "high";
  prefers_examples: boolean;
  teaching_style: "socratic" | "direct" | "blended";
};

export type Account = {
  id: string;
  email: string;
  learner_id: string;
  created_at: string;
};

export type TopicState = {
  mastery: number;
  confidence: number;
  last_practiced_at: string | null;
};

export type ObjectiveState = {
  mastery: number;
  confidence: number;
  last_practiced_at: string | null;
};

export type EvaluationResult = {
  correctness: number;
  confidence: number;
  objective_id: string | null;
  misconception_detected: boolean;
  misconception_description: string | null;
  reasoning: string;
};

export type TutorTurn = {
  id: string;
  learner_message: string;
  tutor_action: string;
  tutor_response: string;
  evaluation: EvaluationResult;
  created_at: string;
};

export type Learner = {
  id: string;
  name: string;
  goal: string;
  skills: Record<string, TopicState>;
  objective_states: Record<string, ObjectiveState>;
  misconceptions: Array<{
    topic: string;
    description: string;
    severity: number;
    created_at: string;
  }>;
  learning_style: LearningPreferences;
  created_at: string;
  updated_at: string;
};

export type Session = {
  id: string;
  learner_id: string;
  topic: string;
  mode: "learn" | "ask" | "test" | "review";
  turns: TutorTurn[];
  created_at: string;
  updated_at: string;
};

export type ConceptObjective = {
  id: string;
  concept_id: string | null;
  slug: string;
  title: string;
  description: string;
  mastery_threshold: number;
};

export type Concept = {
  id: string;
  slug: string;
  title: string;
  description: string;
  subject: string;
  prerequisites: string[];
  objectives: ConceptObjective[];
  created_at: string;
};

export type LessonPlanStep = {
  id: string;
  title: string;
  objective_id: string | null;
  objective_slug: string | null;
  instruction: string;
  rationale: string;
  step_type: "explain" | "diagnostic" | "practice" | "review" | "advance";
};

export type GenerationTrace = {
  provider: string;
  model: string;
  prompt_version: string;
  prompt_inputs: Record<string, unknown>;
};

export type LessonPlan = {
  id: string;
  learner_id: string;
  topic: string;
  status: "active" | "superseded";
  summary: string;
  steps: LessonPlanStep[];
  current_step_index: number;
  completed_step_ids: string[];
  trace: GenerationTrace | null;
  created_at: string;
  updated_at: string;
};

export type ObjectiveProgress = {
  objective: ConceptObjective;
  mastery: number;
  confidence: number;
  last_practiced_at: string | null;
  is_ready: boolean;
};

export type TopicProgress = {
  concept: Concept;
  objectives: ObjectiveProgress[];
  concept_mastery: number;
  concept_confidence: number;
  ready_to_advance: boolean;
};

export type ReviewItem = {
  id: string;
  learner_id: string;
  topic: string;
  due_at: string;
  status: "due" | "scheduled";
  interval_days: number;
  review_count: number;
  last_reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SupplementalMaterial = {
  id: string;
  title: string;
  material_type: "reading" | "video" | "exercise" | "comparison" | "reflection";
  description: string;
  rationale: string;
  query: string;
};

export type SubmitTurnResponse = {
  session_id: string;
  tutor_action: string;
  tutor_response: string;
  evaluation: EvaluationResult;
  active_lesson_step: LessonPlanStep | null;
  updated_learner: Learner;
  updated_session: Session;
};

export type AuthPayload = {
  token: string;
  account: Account;
  learner: Learner;
};
