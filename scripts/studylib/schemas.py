from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "2.0"

EVENT_TYPES = {
    "course_initialized", "material_ingested", "source_registered", "kc_created",
    "kc_updated", "profile_updated", "session_started", "session_finished",
    "question_registered", "question_presented", "confidence_recorded",
    "question_attempted", "answer_graded", "hint_requested",
    "misconception_identified", "repair_started", "repair_step_completed",
    "repair_completed", "transfer_test_created", "transfer_test_attempted",
    "fsrs_card_created", "fsrs_reviewed", "milestone_created", "milestone_updated",
    "mock_exam_created", "mock_exam_completed", "exam_feedback_submitted",
    "state_recalibrated", "attempt_package_imported", "state_rebuilt",
}

ERROR_TYPES = {
    "concept_misconception", "prerequisite_gap", "condition_misread",
    "procedure_omission", "formula_misuse", "representation_failure",
    "transfer_failure", "similar_concept_confusion", "calculation_slip",
    "memory_failure", "strategy_failure", "time_pressure_failure",
    "careless_error", "unknown",
}

TRANSFER_LEVELS = ("T0", "T1", "T2", "T3", "T4")

TRANSFER_KEY = {
    "T0": "T0_original", "T1": "T1_near", "T2": "T2_structural",
    "T3": "T3_discrimination", "T4": "T4_far",
}

CHANGED_DIMENSIONS = {
    "surface_context", "information_structure", "question_direction",
    "condition_combination", "reasoning_order", "representation",
    "distractor_mechanism", "required_identification",
}

SOURCE_TYPES = {
    "syllabus", "textbook", "lecture_slide", "course_note", "homework",
    "past_exam", "teacher_emphasis", "student_input", "synthetic",
    "external_reference",
}

CARD_TYPES = {
    "original_question", "transfer_question", "concept_recall",
    "procedure_recall", "misconception_check",
}


class Event(BaseModel):
    schema_version: str = SCHEMA_VERSION
    event_id: str
    timestamp: str
    event_type: str
    course_id: str
    session_id: str = "session_adhoc"
    actor: str = "student"
    source: str = "main_session"
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"unknown event_type: {v}")
        return v


class ValidationBlock(BaseModel):
    generator: dict[str, Any]
    independent_solver: dict[str, Any]
    adversarial_review: dict[str, Any]
    mechanical_validator: dict[str, Any] | None = None


class Question(BaseModel):
    schema_version: str = SCHEMA_VERSION
    question_id: str
    kc_ids: list[str]
    source_type: str
    transfer_level: Literal["T0", "T1", "T2", "T3", "T4"] = "T0"
    stem: str
    answer: str
    solution: str = ""
    difficulty: float = 0.5
    estimated_minutes: float = 5.0
    changed_dimensions: list[str] = Field(default_factory=list)
    preserved_dimensions: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    source_id: str | None = None
    validation: ValidationBlock | None = None

    @field_validator("source_type")
    @classmethod
    def _known_source_type(cls, v: str) -> str:
        if v not in SOURCE_TYPES:
            raise ValueError(f"unknown source_type: {v}")
        return v

    @field_validator("changed_dimensions")
    @classmethod
    def _known_dimensions(cls, v: list[str]) -> list[str]:
        bad = [d for d in v if d not in CHANGED_DIMENSIONS]
        if bad:
            raise ValueError(f"unknown changed_dimensions: {bad}")
        return v
