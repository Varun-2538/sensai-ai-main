# Enhanced assessment routes extending existing quiz functionality

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import json

from pydantic import BaseModel
from ..db.task import get_task
from ..utils.db import execute_db_operation, get_new_db_connection

router = APIRouter(prefix="/quiz", tags=["quiz_assessment"])

# Pydantic models for request/response
class StartAssessmentRequest(BaseModel):
    task_id: int
    cohort_id: Optional[int] = None
    integrity_monitoring: bool = False
    user_id: Optional[int] = None

class QuestionResponseRequest(BaseModel):
    session_id: str
    question_id: int
    response_data: Dict[str, Any]

# Start an assessment session (extends existing quiz functionality)
@router.post("/assessment/start")
async def start_assessment_session(request: StartAssessmentRequest):
    """Start a new timed assessment session for a quiz task"""
    
    # Get task details to verify it's a quiz
    task = await get_task(request.task_id)
    if not task or task.get('type') != 'quiz':
        raise HTTPException(status_code=404, detail="Quiz task not found")
    
    # Check if task is in assessment mode
    assessment_mode = task.get('assessment_mode', False)
    if not assessment_mode:
        raise HTTPException(status_code=400, detail="Task is not configured for assessment mode")
    
    session_id = str(uuid.uuid4())
    duration_minutes = task.get('duration_minutes', 60)
    
    # Check if user already has an active session for this task
    existing_session = await execute_db_operation(
        "SELECT id, duration_minutes, integrity_session_id FROM assessment_sessions WHERE task_id = ? AND status = 'active'",
        (request.task_id,),
        fetch_one=True
    )
    
    if existing_session:
        # Idempotent behavior: return the existing active session instead of erroring
        return {
            "session_id": existing_session[0],
            "duration_minutes": existing_session[1] or duration_minutes,
            "integrity_session_id": existing_session[2],
            "questions": task.get('questions', []),
            "task": task
        }
    
    # Create integrity session if monitoring enabled
    integrity_session_id = None
    if request.integrity_monitoring and task.get('integrity_monitoring', False):
        try:
            # Create integrity session using DB layer to ensure a session_uuid is returned
            from ..db.integrity import create_integrity_session as create_integrity_session_db
            integrity_session_uuid = await create_integrity_session_db(
                user_id=request.user_id or 1,  # TODO: Replace with authenticated user id
                cohort_id=request.cohort_id,
                task_id=request.task_id,
                monitoring_config={"source": "assessment"}
            )
            integrity_session_id = integrity_session_uuid
        except Exception as e:
            print(f"Failed to create integrity session: {e}")
    
    # Store assessment session in database
    await execute_db_operation(
        """INSERT INTO assessment_sessions 
           (id, task_id, user_id, cohort_id, integrity_session_id, duration_minutes, 
            time_remaining_seconds, status, created_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, request.task_id, request.user_id or 1, request.cohort_id,
         integrity_session_id, duration_minutes, duration_minutes * 60, 'active', 
         datetime.now().isoformat())
    )
    
    return {
        "session_id": session_id,
        "duration_minutes": duration_minutes,
        "integrity_session_id": integrity_session_id,
        "questions": task.get('questions', []),
        "task": task
    }

# Submit response to a question
@router.post("/assessment/{session_id}/response")
async def submit_question_response(session_id: str, request: QuestionResponseRequest):
    """Submit a response to a specific question in an assessment"""
    
    # Validate session exists and is active
    session = await execute_db_operation(
        "SELECT * FROM assessment_sessions WHERE id = ? AND status = 'active'",
        (session_id,),
        fetch_one=True
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found or inactive")
    
    question_id = request.question_id
    response_data = request.response_data
    
    # Store response in database
    response_id = await execute_db_operation(
        """INSERT INTO question_responses 
           (session_id, question_id, response_type, response_data, submitted_at) 
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, question_id, response_data.get('type', 'text'), 
         json.dumps(response_data), datetime.now().isoformat()),
        return_last_id=True
    )
    
    # Auto-grade if possible
    score = None
    max_score = 10  # Default, should get from question config
    
    if response_data.get('type') == 'mcq':
        # Auto-grade MCQ by checking against correct answers
        question_details = await execute_db_operation(
            "SELECT * FROM questions WHERE id = ?",
            (question_id,),
            fetch_one=True
        )
        
        if question_details:
            # Get MCQ options for this question
            mcq_options = await execute_db_operation(
                "SELECT * FROM mcq_options WHERE question_id = ?",
                (question_id,),
                fetch_all=True
            )
            
            if mcq_options:
                correct_options = [opt[0] for opt in mcq_options if opt[3]]  # is_correct column
                selected_options = response_data.get('selected_options', [])
                
                # Simple scoring: full points if all correct, 0 otherwise
                if set(selected_options) == set(str(opt) for opt in correct_options):
                    score = max_score
                else:
                    score = 0
                
                # Update response with score
                await execute_db_operation(
                    "UPDATE question_responses SET score = ?, max_score = ?, auto_graded = 1 WHERE id = ?",
                    (score, max_score, response_id)
                )
    
    return {
        "status": "saved", 
        "response_id": response_id,
        "score": score,
        "max_score": max_score
    }

# Submit entire assessment
@router.post("/assessment/{session_id}/submit")
async def submit_assessment(session_id: str):
    """Submit the entire assessment and calculate score"""
    
    # Get session details
    session = await execute_db_operation(
        "SELECT * FROM assessment_sessions WHERE id = ? AND status = 'active'",
        (session_id,),
        fetch_one=True
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found or already submitted")
    
    # Get all responses for this session
    responses = await execute_db_operation(
        "SELECT * FROM question_responses WHERE session_id = ?",
        (session_id,),
        fetch_all=True
    )
    
    # Calculate total score
    total_score = 0
    max_score = 0
    correct_answers = 0
    
    for response in responses:
        response_score = response[7] if response[7] is not None else 0  # score column
        response_max = response[8] if response[8] is not None else 10   # max_score column
        
        total_score += response_score
        max_score += response_max
        
        if response_score == response_max:
            correct_answers += 1
    
    # Calculate time spent
    start_time = datetime.fromisoformat(session[5])  # started_at column
    time_spent_minutes = int((datetime.now() - start_time).total_seconds() / 60)
    
    # Update session status
    await execute_db_operation(
        """UPDATE assessment_sessions 
           SET status = 'submitted', submitted_at = ?, total_score = ?, max_score = ?, updated_at = ?
           WHERE id = ?""",
        ('submitted', datetime.now().isoformat(), total_score, max_score, 
         datetime.now().isoformat(), session_id)
    )
    
    # Store analytics
    await execute_db_operation(
        """INSERT INTO assessment_analytics 
           (task_id, session_id, total_questions, answered_questions, correct_answers, 
            total_score, max_score, time_spent_minutes, calculated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session[1], session_id, len(responses), len(responses), correct_answers,
         total_score, max_score, time_spent_minutes, datetime.now().isoformat())
    )
    
    # Mark task completion (best-effort) and calculate pass/fail based on task's passing score
    task = await get_task(session[1])  # task_id column
    passing_percentage = task.get('passing_score_percentage', 60)
    passed = (total_score / max_score * 100) >= passing_percentage if max_score > 0 else False

    # Insert completion record for the task
    try:
        from ..config import task_completions_table_name
        await execute_db_operation(
            f"""
            INSERT OR IGNORE INTO {task_completions_table_name} (user_id, task_id)
            VALUES (?, ?)
            """,
            (session[2], session[1])  # user_id, task_id
        )
    except Exception as e:
        print(f"Failed to record task completion for assessment session {session_id}: {e}")
    
    return {
        "status": "submitted",
        "total_score": total_score,
        "max_score": max_score,
        "percentage": round(total_score / max_score * 100, 2) if max_score > 0 else 0,
        "passed": passed,
        "time_spent_minutes": time_spent_minutes,
        "correct_answers": correct_answers,
        "total_questions": len(responses)
    }

# Get assessment session status
@router.get("/assessment/{session_id}/status")
async def get_assessment_session_status(session_id: str):
    """Get current assessment session details"""
    
    session = await execute_db_operation(
        "SELECT * FROM assessment_sessions WHERE id = ?",
        (session_id,),
        fetch_one=True
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found")
    
    # Count responses
    responses = await execute_db_operation(
        "SELECT COUNT(*) FROM question_responses WHERE session_id = ?",
        (session_id,),
        fetch_one=True
    )
    answered_count = responses[0] if responses else 0
    
    # Get task to find total questions
    task = await get_task(session[1])  # task_id
    total_questions = len(task.get('questions', [])) if task else 0
    
    return {
        "session_id": session_id,
        "status": session[8],  # status column
        "time_remaining_seconds": session[7],  # time_remaining_seconds column
        "answered_questions": answered_count,
        "total_questions": total_questions,
        "started_at": session[5]  # started_at column
    }

# Assessment analytics for admins
@router.get("/tasks/{task_id}/analytics")
async def get_assessment_analytics(task_id: int):
    """Get assessment analytics for a specific task"""
    
    # Get all assessment sessions for this task
    sessions = await execute_db_operation(
        "SELECT * FROM assessment_sessions WHERE task_id = ? AND status = 'submitted'",
        (task_id,),
        fetch_all=True
    )
    
    if not sessions:
        return {
            "task_id": task_id,
            "total_attempts": 0,
            "average_score": 0,
            "pass_rate": 0,
            "average_time_minutes": 0
        }
    
    # Calculate analytics
    total_attempts = len(sessions)
    total_score = sum(session[9] or 0 for session in sessions)  # total_score column
    max_possible = sum(session[10] or 0 for session in sessions)  # max_score column
    
    average_score = (total_score / max_possible * 100) if max_possible > 0 else 0
    
    # Get task passing percentage
    task = await get_task(task_id)
    passing_percentage = task.get('passing_score_percentage', 60)
    
    passed_count = 0
    total_time = 0
    
    for session in sessions:
        session_score = session[9] or 0
        session_max = session[10] or 0
        session_percentage = (session_score / session_max * 100) if session_max > 0 else 0
        
        if session_percentage >= passing_percentage:
            passed_count += 1
        
        # Calculate time spent for this session
        start_time = datetime.fromisoformat(session[5])
        submit_time = datetime.fromisoformat(session[6]) if session[6] else datetime.now()
        session_time = int((submit_time - start_time).total_seconds() / 60)
        total_time += session_time
    
    pass_rate = passed_count / total_attempts if total_attempts > 0 else 0
    average_time = total_time / total_attempts if total_attempts > 0 else 0
    
    return {
        "task_id": task_id,
        "total_attempts": total_attempts,
        "average_score": round(average_score, 2),
        "pass_rate": round(pass_rate, 2),
        "average_time_minutes": round(average_time, 2)
    }
