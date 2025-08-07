"""
API routes for integrity monitoring and proctoring
"""
from fastapi import APIRouter, HTTPException, status
from typing import List, Optional
from datetime import datetime

from api.models import (
    CreateIntegritySessionRequest,
    CreateProctorEventRequest,
    BatchProctorEventsRequest,
    CreateIntegrityFlagRequest,
    UpdateFlagDecisionRequest,
    UpdateSessionStatusRequest,
    IntegritySessionResponse,
    ProctorEventResponse,
    IntegrityFlagResponse,
    SessionAnalysisResponse,
    CohortIntegrityOverviewResponse,
    EventType,
    SeverityLevel,
    FlagType,
    SessionStatus,
    ReviewerDecision,
    GazeAnalysisRequest,
    GazeAnalysisResponse,
    MouseDriftAnalysisRequest,
    MouseDriftAnalysisResponse,
)

from api.db.integrity import (
    create_integrity_session,
    get_integrity_session,
    update_session_status,
    get_active_sessions_for_user,
    create_proctor_event,
    create_batch_proctor_events,
    get_session_events,
    get_user_events,
    create_integrity_flag,
    update_flag_decision,
    get_session_flags,
    get_pending_flags,
    get_session_analysis,
    get_cohort_integrity_overview,
)

router = APIRouter()


# Helper function to convert database records to response models
def convert_session_to_response(session_data: dict) -> IntegritySessionResponse:
    """Convert database session data to response model"""
    return IntegritySessionResponse(
        id=session_data['id'],
        session_uuid=session_data['session_uuid'],
        user_id=session_data['user_id'],
        cohort_id=session_data['cohort_id'],
        task_id=session_data['task_id'],
        monitoring_config=session_data['monitoring_config'],
        session_start=session_data['session_start'],
        session_end=session_data['session_end'],
        status=SessionStatus(session_data['status'])
    )


def convert_event_to_response(event_data: dict) -> ProctorEventResponse:
    """Convert database event data to response model"""
    return ProctorEventResponse(
        id=event_data['id'],
        session_uuid=event_data['session_uuid'],
        user_id=event_data['user_id'],
        event_type=EventType(event_data['event_type']),
        timestamp=event_data['timestamp'],
        data=event_data['data'],
        severity=SeverityLevel(event_data['severity']),
        flagged=bool(event_data['flagged'])
    )


def convert_flag_to_response(flag_data: dict) -> IntegrityFlagResponse:
    """Convert database flag data to response model"""
    return IntegrityFlagResponse(
        id=flag_data['id'],
        session_uuid=flag_data['session_uuid'],
        user_id=flag_data['user_id'],
        flag_type=FlagType(flag_data['flag_type']),
        confidence_score=flag_data['confidence_score'],
        evidence=flag_data['evidence'],
        reviewer_decision=ReviewerDecision(flag_data['reviewer_decision']) if flag_data['reviewer_decision'] else None,
        created_at=flag_data['created_at'],
        reviewed_at=flag_data['reviewed_at']
    )


# Session Management Endpoints

@router.post("/sessions", response_model=IntegritySessionResponse)
async def create_session(
    request: CreateIntegritySessionRequest
):
    """Create a new integrity monitoring session"""
    try:
        # TODO: Add authentication and permission checking
        
        session_uuid = await create_integrity_session(
            user_id=request.user_id,
            cohort_id=request.cohort_id,
            task_id=request.task_id,
            monitoring_config=request.monitoring_config
        )
        
        session_data = await get_integrity_session(session_uuid)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create session"
            )
        
        return convert_session_to_response(session_data)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create integrity session: {str(e)}"
        )


@router.get("/sessions/{session_uuid}", response_model=IntegritySessionResponse)
async def get_session(
    session_uuid: str
):
    """Get integrity session details"""
    session_data = await get_integrity_session(session_uuid)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # TODO: Add authentication and permission checking
    
    return convert_session_to_response(session_data)


@router.put("/sessions/{session_uuid}/status")
async def update_session_status_endpoint(
    session_uuid: str,
    request: UpdateSessionStatusRequest
):
    """Update session status"""
    session_data = await get_integrity_session(session_uuid)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # TODO: Add authentication and permission checking
    
    try:
        await update_session_status(
            session_uuid=session_uuid,
            status=request.status.value,
            session_end=request.session_end
        )
        return {"message": "Session status updated successfully"}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session status: {str(e)}"
        )


@router.get("/users/{user_id}/sessions", response_model=List[IntegritySessionResponse])
async def get_user_sessions(
    user_id: int
):
    """Get all active sessions for a user"""
    # TODO: Add authentication and permission checking
    
    sessions_data = await get_active_sessions_for_user(user_id)
    return [convert_session_to_response(session) for session in sessions_data]


# Event Management Endpoints

@router.post("/events")
async def create_event(
    request: CreateProctorEventRequest
):
    """Create a new proctor event"""
    try:
        # Verify session exists
        session_data = await get_integrity_session(request.session_uuid)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # TODO: Add authentication and permission checking
        
        event_id = await create_proctor_event(
            session_uuid=request.session_uuid,
            user_id=request.user_id,
            event_type=request.event_type.value,
            data=request.data,
            severity=request.severity.value,
            flagged=request.flagged
        )
        
        return {"event_id": event_id, "message": "Event created successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event: {str(e)}"
        )


@router.post("/events/batch")
async def create_batch_events(
    request: BatchProctorEventsRequest
):
    """Create multiple proctor events in a batch"""
    try:
        # Verify all events belong to valid sessions
        session_uuids = set(event.session_uuid for event in request.events)
        for session_uuid in session_uuids:
            session_data = await get_integrity_session(session_uuid)
            if not session_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {session_uuid} not found"
                )
        
        # TODO: Add authentication and permission checking
        
        # Convert events to database format
        events_data = []
        for event in request.events:
            
            events_data.append({
                'session_uuid': event.session_uuid,
                'user_id': event.user_id,
                'event_type': event.event_type.value,
                'data': event.data,
                'severity': event.severity.value,
                'flagged': event.flagged
            })
        
        event_ids = await create_batch_proctor_events(events_data)
        
        return {
            "event_ids": event_ids,
            "count": len(event_ids),
            "message": "Batch events created successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create batch events: {str(e)}"
        )


@router.get("/sessions/{session_uuid}/events", response_model=List[ProctorEventResponse])
async def get_session_events_endpoint(
    session_uuid: str,
    event_type: Optional[EventType] = None,
    flagged_only: bool = False,
    limit: int = 1000,

):
    """Get events for a session"""
    # Verify session exists and user has permission
    session_data = await get_integrity_session(session_uuid)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # TODO: Add authentication and permission checking
    
    events_data = await get_session_events(
        session_uuid=session_uuid,
        event_type=event_type.value if event_type else None,
        flagged_only=flagged_only,
        limit=limit
    )
    
    return [convert_event_to_response(event) for event in events_data]


@router.get("/users/{user_id}/events", response_model=List[ProctorEventResponse])
async def get_user_events_endpoint(
    user_id: int,
    event_type: Optional[EventType] = None,
    flagged_only: bool = False,
    limit: int = 1000,

):
    """Get events for a user across all sessions"""
    # Verify user has permission to view these events
    # TODO: Add authentication and permission checking
    
    events_data = await get_user_events(
        user_id=user_id,
        event_type=event_type.value if event_type else None,
        flagged_only=flagged_only,
        limit=limit
    )
    
    return [convert_event_to_response(event) for event in events_data]


# Flag Management Endpoints

@router.post("/flags")
async def create_flag(
    request: CreateIntegrityFlagRequest,

):
    """Create a new integrity flag"""
    try:
        # Verify session exists
        session_data = await get_integrity_session(request.session_uuid)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        flag_id = await create_integrity_flag(
            session_uuid=request.session_uuid,
            user_id=request.user_id,
            flag_type=request.flag_type.value,
            confidence_score=request.confidence_score,
            evidence=request.evidence
        )
        
        return {"flag_id": flag_id, "message": "Flag created successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create flag: {str(e)}"
        )


@router.put("/flags/{flag_id}/decision")
async def update_flag_decision_endpoint(
    flag_id: int,
    request: UpdateFlagDecisionRequest,

):
    """Update flag with reviewer decision"""
    try:
        # TODO: Add authentication and permission checking
        
        success = await update_flag_decision(flag_id, request.reviewer_decision.value)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flag not found"
            )
        
        return {"message": "Flag decision updated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update flag decision: {str(e)}"
        )


@router.get("/sessions/{session_uuid}/flags", response_model=List[IntegrityFlagResponse])
async def get_session_flags_endpoint(
    session_uuid: str,

):
    """Get all flags for a session"""
    # Verify session exists and user has permission
    session_data = await get_integrity_session(session_uuid)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # TODO: Add authentication and permission checking
    
    flags_data = await get_session_flags(session_uuid)
    return [convert_flag_to_response(flag) for flag in flags_data]


@router.get("/flags/pending", response_model=List[IntegrityFlagResponse])
async def get_pending_flags_endpoint(

):
    """Get all flags pending review"""
    # TODO: Add permission checking for reviewers/admins
    
    flags_data = await get_pending_flags()
    return [convert_flag_to_response(flag) for flag in flags_data]


# Analysis Endpoints

@router.get("/sessions/{session_uuid}/analysis", response_model=SessionAnalysisResponse)
async def get_session_analysis_endpoint(
    session_uuid: str,

):
    """Get comprehensive analysis for a session"""
    # Verify session exists and user has permission
    session_data = await get_integrity_session(session_uuid)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # TODO: Add authentication and permission checking
    
    try:
        analysis_data = await get_session_analysis(session_uuid)
        if not analysis_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not available"
            )
        
        # Convert data to response models
        session_response = convert_session_to_response(analysis_data['session'])
        recent_events = [convert_event_to_response(event) for event in analysis_data['recent_events']]
        flags = [convert_flag_to_response(flag) for flag in analysis_data['flags']]
        
        return SessionAnalysisResponse(
            session=session_response,
            integrity_score=analysis_data['integrity_score'],
            total_events=analysis_data['total_events'],
            flagged_events=analysis_data['flagged_events'],
            flags_count=analysis_data['flags_count'],
            event_types=analysis_data['event_types'],
            severity_distribution=analysis_data['severity_distribution'],
            recent_events=recent_events,
            flags=flags
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session analysis: {str(e)}"
        )


@router.get("/cohorts/{cohort_id}/integrity-overview", response_model=CohortIntegrityOverviewResponse)
async def get_cohort_overview(
    cohort_id: int,
    include_details: bool = False,

):
    """Get integrity overview for a cohort"""
    # TODO: Add authentication and permission checking
    
    try:
        overview_data = await get_cohort_integrity_overview(cohort_id)
        
        session_analyses = None
        if include_details and overview_data.get('session_analyses'):
            session_analyses = []
            for analysis in overview_data['session_analyses']:
                session_response = convert_session_to_response(analysis['session'])
                recent_events = [convert_event_to_response(event) for event in analysis['recent_events']]
                flags = [convert_flag_to_response(flag) for flag in analysis['flags']]
                
                session_analyses.append(SessionAnalysisResponse(
                    session=session_response,
                    integrity_score=analysis['integrity_score'],
                    total_events=analysis['total_events'],
                    flagged_events=analysis['flagged_events'],
                    flags_count=analysis['flags_count'],
                    event_types=analysis['event_types'],
                    severity_distribution=analysis['severity_distribution'],
                    recent_events=recent_events,
                    flags=flags
                ))
        
        return CohortIntegrityOverviewResponse(
            cohort_id=overview_data['cohort_id'],
            total_sessions=overview_data['total_sessions'],
            average_integrity_score=overview_data['average_integrity_score'],
            total_flags=overview_data['total_flags'],
            sessions_with_issues=overview_data['sessions_with_issues'],
            session_analyses=session_analyses
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cohort overview: {str(e)}"
        )


# Health Check Endpoint

@router.get("/health")
async def integrity_health_check():
    """Health check for integrity monitoring system"""
    return {
        "status": "ok",
        "service": "integrity-monitoring",
        "timestamp": datetime.utcnow().isoformat()
    }


# Analysis Endpoints (stateless heuristics + optional event creation)

from api.utils.integrity_analysis import analyze_gaze_data, analyze_mouse_drift


@router.post("/analyze/gaze", response_model=GazeAnalysisResponse)
async def analyze_gaze(request: GazeAnalysisRequest):
    """Analyze gaze from landmarks/head pose server-side and optionally create an event."""
    # Validate session exists
    session_data = await get_integrity_session(request.session_uuid)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    looking_away, confidence, metrics = analyze_gaze_data(
        face_landmarks=[lm.dict() for lm in request.face_landmarks] if request.face_landmarks else None,
        euler_angles=request.euler_angles.dict() if request.euler_angles else None,
        config=request.config or {},
    )

    # Optionally record event based on threshold
    threshold = float((request.config or {}).get("event_threshold", 0.7))
    if looking_away and confidence >= threshold:
        await create_proctor_event(
            session_uuid=request.session_uuid,
            user_id=request.user_id,
            event_type=EventType.LOOKING_AWAY.value,
            data={"metrics": metrics, "confidence": confidence},
            severity=SeverityLevel.MEDIUM.value,
            flagged=True,
        )

    return GazeAnalysisResponse(
        looking_away=bool(looking_away),
        confidence=float(confidence),
        metrics=metrics,
    )


@router.post("/analyze/mouse-drift", response_model=MouseDriftAnalysisResponse)
async def analyze_mouse_drift_endpoint(request: MouseDriftAnalysisRequest):
    """Analyze mouse samples for drifting server-side and optionally create an event."""
    # Validate session exists
    session_data = await get_integrity_session(request.session_uuid)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    is_drift, drift_score, metrics = analyze_mouse_drift(
        samples=[s.dict() for s in request.samples],
        screen_width=request.screen_width,
        screen_height=request.screen_height,
        config=request.config or {},
    )

    # Optionally record event based on threshold
    threshold = float((request.config or {}).get("event_threshold", 0.7))
    if is_drift and drift_score >= threshold:
        await create_proctor_event(
            session_uuid=request.session_uuid,
            user_id=request.user_id,
            event_type=EventType.MOUSE_DRIFT.value,
            data={"metrics": metrics, "drift_score": drift_score},
            severity=SeverityLevel.MEDIUM.value,
            flagged=True,
        )

    return MouseDriftAnalysisResponse(
        is_drift=bool(is_drift),
        drift_score=float(drift_score),
        metrics=metrics,
    )
