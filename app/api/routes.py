from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.models.api import (
    CreateLearnerRequest,
    CreateSessionRequest,
    LearnerResponse,
    SessionResponse,
    SubmitTurnRequest,
    SubmitTurnResponse,
)
from app.services.database import get_db_session
from app.services.dependencies import (
    get_learner_repository,
    get_orchestrator,
    get_session_repository,
)

api_router = APIRouter(prefix="/api/v1")


@api_router.post("/learners", response_model=LearnerResponse)
def create_learner(
    payload: CreateLearnerRequest, db: DbSession = Depends(get_db_session)
) -> LearnerResponse:
    learner = get_learner_repository(db).create(payload)
    return LearnerResponse.model_validate(learner)


@api_router.get("/learners/{learner_id}", response_model=LearnerResponse)
def get_learner(learner_id: str, db: DbSession = Depends(get_db_session)) -> LearnerResponse:
    learner = get_learner_repository(db).get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    return LearnerResponse.model_validate(learner)


@api_router.post("/sessions", response_model=SessionResponse)
def create_session(
    payload: CreateSessionRequest, db: DbSession = Depends(get_db_session)
) -> SessionResponse:
    learner = get_learner_repository(db).get(payload.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    session = get_session_repository(db).create(payload)
    return SessionResponse.model_validate(session)


@api_router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db: DbSession = Depends(get_db_session)) -> SessionResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse.model_validate(session)


@api_router.post("/sessions/{session_id}/turns", response_model=SubmitTurnResponse)
def submit_turn(
    session_id: str,
    payload: SubmitTurnRequest,
    db: DbSession = Depends(get_db_session),
) -> SubmitTurnResponse:
    session = get_session_repository(db).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    learner = get_learner_repository(db).get(session.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    result = get_orchestrator(db).handle_turn(
        session_id=session_id,
        learner=learner,
        session=session,
        learner_message=payload.message,
        requested_mode=payload.mode,
    )
    return SubmitTurnResponse.model_validate(result)
