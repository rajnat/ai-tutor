from dataclasses import dataclass


@dataclass(frozen=True)
class TutorConfig:
    # New learner baseline (no prior exposure)
    initial_topic_mastery: float = 0.1
    initial_topic_confidence: float = 0.1
    # Learner who explicitly named a topic at signup (some prior exposure)
    initial_known_topic_mastery: float = 0.2
    initial_known_topic_confidence: float = 0.2

    # Topic-level mastery update
    mastery_neutral_correctness: float = 0.5   # correctness at which mastery stays flat
    mastery_update_scale: float = 0.2          # step size per evaluation
    confidence_blend_factor: float = 0.4       # weight of new confidence signal vs retained
    misconception_severity_floor: float = 0.3  # minimum recorded severity

    # Objective-level mastery update (more conservative neutral point)
    objective_neutral_correctness: float = 0.3

    # Curriculum action thresholds
    mastery_novice_threshold: float = 0.3        # below → EXPLAIN
    mastery_intermediate_threshold: float = 0.7  # below → ASK_DIAGNOSTIC; above → ADVANCE
    mastery_complete_threshold: float = 0.8      # "done" — skip in suggestions, ready to advance
    prerequisite_mastery_threshold: float = 0.6  # min prereq mastery before a concept is offered

    # Spillover objective updates
    spillover_min_correctness: float = 0.6  # must exceed this to update non-focused objectives
    spillover_high_boundary: float = 0.7    # above → strong spillover; below → weak spillover
    spillover_scale_high: float = 0.8
    spillover_scale_low: float = 0.35

    # Lesson plan step completion thresholds
    step_complete_objective_threshold: float = 0.7   # objective-focused step
    step_complete_generic_threshold: float = 0.75    # diagnostic / practice / review step
    step_complete_explain_threshold: float = 0.65    # explain step

    # Review scheduling
    review_short_interval_boundary: float = 0.5    # below → 1-day interval
    review_medium_interval_boundary: float = 0.75   # below → 3-day; above → 7-day
    review_double_interval_threshold: float = 0.8   # above → double interval on completion
    review_grow_interval_threshold: float = 0.6     # above → grow by 1
    review_reschedule_threshold: float = 0.5        # below → mark DUE immediately

    # Checkpoint evaluation scores (used when the answer is unambiguously right/wrong)
    checkpoint_correct_correctness: float = 0.9
    checkpoint_correct_confidence: float = 0.8
    checkpoint_wrong_correctness: float = 0.25
    checkpoint_wrong_confidence: float = 0.35

    # Degraded-mode placeholder (LLM unreachable during evaluation)
    degraded_evaluation_confidence: float = 0.2

    # Prerequisite placement quiz
    placement_max_turns: int = 3  # diagnostic turns before resolving placement

    # Misconception lifecycle
    misconception_max_per_topic: int = 5               # hard cap; oldest dropped when exceeded
    misconception_resolution_correctness: float = 0.82 # correctness required to resolve one misconception
    misconception_resolution_confidence: float = 0.55  # minimum confidence to trigger resolution
    misconception_dedup_similarity: float = 0.45       # Jaccard threshold for near-duplicate detection

    # Adaptive difficulty — misconception and confidence signals
    difficulty_low_confidence_threshold: float = 0.35  # below this, don't ADVANCE
    difficulty_high_misconception_count: int = 2        # at or above this, force REINFORCE
    difficulty_misconception_window: int = 5            # how many recent topic misconceptions to inspect

    # Learning pace assessment
    pace_recent_turns_window: int = 4            # rolling window for avg correctness
    pace_struggling_avg_correctness: float = 0.4  # rolling avg below this → STRUGGLING
    pace_accelerating_avg_correctness: float = 0.75  # rolling avg at or above this → ACCELERATING
    pace_struggling_turns_minimum: int = 5        # turns needed before declaring "stuck at novice"


DEFAULT_CONFIG = TutorConfig()
