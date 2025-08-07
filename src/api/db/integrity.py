"""
Database operations for integrity monitoring and proctoring
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from api.utils.db import get_new_db_connection
from api.config import (
    integrity_sessions_table_name,
    proctor_events_table_name,
    integrity_flags_table_name,
    users_table_name,
    cohorts_table_name,
    tasks_table_name,
)


async def create_integrity_sessions_table(cursor):
    """Create integrity sessions table"""
    await cursor.execute(
        f"""CREATE TABLE IF NOT EXISTS {integrity_sessions_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_uuid TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                cohort_id INTEGER,
                task_id INTEGER,
                monitoring_config TEXT,
                session_start DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_end DATETIME,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (user_id) REFERENCES {users_table_name}(id) ON DELETE CASCADE,
                FOREIGN KEY (cohort_id) REFERENCES {cohorts_table_name}(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES {tasks_table_name}(id) ON DELETE CASCADE
            )"""
    )

    await cursor.execute(
        f"""CREATE INDEX idx_integrity_session_uuid ON {integrity_sessions_table_name} (session_uuid)"""
    )
    await cursor.execute(
        f"""CREATE INDEX idx_integrity_session_user_id ON {integrity_sessions_table_name} (user_id)"""
    )
    await cursor.execute(
        f"""CREATE INDEX idx_integrity_session_cohort_id ON {integrity_sessions_table_name} (cohort_id)"""
    )


async def create_proctor_events_table(cursor):
    """Create proctor events table"""
    await cursor.execute(
        f"""CREATE TABLE IF NOT EXISTS {proctor_events_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_uuid TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                data TEXT,
                severity TEXT DEFAULT 'medium',
                flagged BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES {users_table_name}(id) ON DELETE CASCADE,
                FOREIGN KEY (session_uuid) REFERENCES {integrity_sessions_table_name}(session_uuid) ON DELETE CASCADE
            )"""
    )

    await cursor.execute(
        f"""CREATE INDEX idx_proctor_event_session_uuid ON {proctor_events_table_name} (session_uuid)"""
    )
    await cursor.execute(
        f"""CREATE INDEX idx_proctor_event_user_id ON {proctor_events_table_name} (user_id)"""
    )
    await cursor.execute(
        f"""CREATE INDEX idx_proctor_event_type ON {proctor_events_table_name} (event_type)"""
    )
    await cursor.execute(
        f"""CREATE INDEX idx_proctor_event_flagged ON {proctor_events_table_name} (flagged)"""
    )


async def create_integrity_flags_table(cursor):
    """Create integrity flags table"""
    await cursor.execute(
        f"""CREATE TABLE IF NOT EXISTS {integrity_flags_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_uuid TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                flag_type TEXT NOT NULL,
                confidence_score REAL DEFAULT 0.0,
                evidence TEXT,
                reviewer_decision TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                reviewed_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES {users_table_name}(id) ON DELETE CASCADE,
                FOREIGN KEY (session_uuid) REFERENCES {integrity_sessions_table_name}(session_uuid) ON DELETE CASCADE
            )"""
    )

    await cursor.execute(
        f"""CREATE INDEX idx_integrity_flag_session_uuid ON {integrity_flags_table_name} (session_uuid)"""
    )
    await cursor.execute(
        f"""CREATE INDEX idx_integrity_flag_user_id ON {integrity_flags_table_name} (user_id)"""
    )
    await cursor.execute(
        f"""CREATE INDEX idx_integrity_flag_type ON {integrity_flags_table_name} (flag_type)"""
    )


# CRUD Operations for Integrity Sessions

async def create_integrity_session(
    user_id: int,
    cohort_id: Optional[int] = None,
    task_id: Optional[int] = None,
    monitoring_config: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new integrity monitoring session"""
    session_uuid = str(uuid.uuid4())
    config_json = json.dumps(monitoring_config) if monitoring_config else None
    
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""INSERT INTO {integrity_sessions_table_name} 
                (session_uuid, user_id, cohort_id, task_id, monitoring_config)
                VALUES (?, ?, ?, ?, ?)""",
            (session_uuid, user_id, cohort_id, task_id, config_json)
        )
        await conn.commit()
    
    return session_uuid


async def get_integrity_session(session_uuid: str) -> Optional[Dict[str, Any]]:
    """Get integrity session by UUID"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""SELECT * FROM {integrity_sessions_table_name} 
                WHERE session_uuid = ?""",
            (session_uuid,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                'id': row[0],
                'session_uuid': row[1],
                'user_id': row[2],
                'cohort_id': row[3],
                'task_id': row[4],
                'monitoring_config': json.loads(row[5]) if row[5] else None,
                'session_start': row[6],
                'session_end': row[7],
                'status': row[8]
            }
        return None


async def update_session_status(session_uuid: str, status: str, session_end: Optional[datetime] = None):
    """Update session status and optionally end time"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        if session_end:
            await cursor.execute(
                f"""UPDATE {integrity_sessions_table_name} 
                    SET status = ?, session_end = ? 
                    WHERE session_uuid = ?""",
                (status, session_end, session_uuid)
            )
        else:
            await cursor.execute(
                f"""UPDATE {integrity_sessions_table_name} 
                    SET status = ? 
                    WHERE session_uuid = ?""",
                (status, session_uuid)
            )
        await conn.commit()


async def get_active_sessions_for_user(user_id: int) -> List[Dict[str, Any]]:
    """Get all active sessions for a user"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""SELECT * FROM {integrity_sessions_table_name} 
                WHERE user_id = ? AND status = 'active'""",
            (user_id,)
        )
        rows = await cursor.fetchall()
        
        sessions = []
        for row in rows:
            sessions.append({
                'id': row[0],
                'session_uuid': row[1],
                'user_id': row[2],
                'cohort_id': row[3],
                'task_id': row[4],
                'monitoring_config': json.loads(row[5]) if row[5] else None,
                'session_start': row[6],
                'session_end': row[7],
                'status': row[8]
            })
        
        return sessions


# CRUD Operations for Proctor Events

async def create_proctor_event(
    session_uuid: str,
    user_id: int,
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
    severity: str = 'medium',
    flagged: bool = False
) -> int:
    """Create a new proctor event"""
    data_json = json.dumps(data) if data else None
    
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""INSERT INTO {proctor_events_table_name} 
                (session_uuid, user_id, event_type, data, severity, flagged)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (session_uuid, user_id, event_type, data_json, severity, flagged)
        )
        await conn.commit()
        return cursor.lastrowid


async def create_batch_proctor_events(events: List[Dict[str, Any]]) -> List[int]:
    """Create multiple proctor events in a batch"""
    event_ids = []
    
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        
        for event in events:
            data_json = json.dumps(event.get('data')) if event.get('data') else None
            await cursor.execute(
                f"""INSERT INTO {proctor_events_table_name} 
                    (session_uuid, user_id, event_type, data, severity, flagged)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event['session_uuid'],
                    event['user_id'],
                    event['event_type'],
                    data_json,
                    event.get('severity', 'medium'),
                    event.get('flagged', False)
                )
            )
            event_ids.append(cursor.lastrowid)
        
        await conn.commit()
    
    return event_ids


async def get_session_events(
    session_uuid: str,
    event_type: Optional[str] = None,
    flagged_only: bool = False,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """Get events for a session"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        
        query = f"""SELECT * FROM {proctor_events_table_name} 
                   WHERE session_uuid = ?"""
        params = [session_uuid]
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        
        if flagged_only:
            query += " AND flagged = TRUE"
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        await cursor.execute(query, params)
        rows = await cursor.fetchall()
        
        events = []
        for row in rows:
            events.append({
                'id': row[0],
                'session_uuid': row[1],
                'user_id': row[2],
                'event_type': row[3],
                'timestamp': row[4],
                'data': json.loads(row[5]) if row[5] else None,
                'severity': row[6],
                'flagged': row[7]
            })
        
        return events


async def get_user_events(
    user_id: int,
    event_type: Optional[str] = None,
    flagged_only: bool = False,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """Get events for a user across all sessions"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        
        query = f"""SELECT * FROM {proctor_events_table_name} 
                   WHERE user_id = ?"""
        params = [user_id]
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        
        if flagged_only:
            query += " AND flagged = TRUE"
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        await cursor.execute(query, params)
        rows = await cursor.fetchall()
        
        events = []
        for row in rows:
            events.append({
                'id': row[0],
                'session_uuid': row[1],
                'user_id': row[2],
                'event_type': row[3],
                'timestamp': row[4],
                'data': json.loads(row[5]) if row[5] else None,
                'severity': row[6],
                'flagged': row[7]
            })
        
        return events


# CRUD Operations for Integrity Flags

async def create_integrity_flag(
    session_uuid: str,
    user_id: int,
    flag_type: str,
    confidence_score: float = 0.0,
    evidence: Optional[Dict[str, Any]] = None
) -> int:
    """Create a new integrity flag"""
    evidence_json = json.dumps(evidence) if evidence else None
    
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""INSERT INTO {integrity_flags_table_name} 
                (session_uuid, user_id, flag_type, confidence_score, evidence)
                VALUES (?, ?, ?, ?, ?)""",
            (session_uuid, user_id, flag_type, confidence_score, evidence_json)
        )
        await conn.commit()
        return cursor.lastrowid


async def update_flag_decision(flag_id: int, reviewer_decision: str) -> bool:
    """Update flag with reviewer decision"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""UPDATE {integrity_flags_table_name} 
                SET reviewer_decision = ?, reviewed_at = CURRENT_TIMESTAMP 
                WHERE id = ?""",
            (reviewer_decision, flag_id)
        )
        await conn.commit()
        return cursor.rowcount > 0


async def get_session_flags(session_uuid: str) -> List[Dict[str, Any]]:
    """Get all flags for a session"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""SELECT * FROM {integrity_flags_table_name} 
                WHERE session_uuid = ? 
                ORDER BY created_at DESC""",
            (session_uuid,)
        )
        rows = await cursor.fetchall()
        
        flags = []
        for row in rows:
            flags.append({
                'id': row[0],
                'session_uuid': row[1],
                'user_id': row[2],
                'flag_type': row[3],
                'confidence_score': row[4],
                'evidence': json.loads(row[5]) if row[5] else None,
                'reviewer_decision': row[6],
                'created_at': row[7],
                'reviewed_at': row[8]
            })
        
        return flags


async def get_pending_flags() -> List[Dict[str, Any]]:
    """Get all flags pending review"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""SELECT * FROM {integrity_flags_table_name} 
                WHERE reviewer_decision IS NULL 
                ORDER BY created_at DESC"""
        )
        rows = await cursor.fetchall()
        
        flags = []
        for row in rows:
            flags.append({
                'id': row[0],
                'session_uuid': row[1],
                'user_id': row[2],
                'flag_type': row[3],
                'confidence_score': row[4],
                'evidence': json.loads(row[5]) if row[5] else None,
                'reviewer_decision': row[6],
                'created_at': row[7],
                'reviewed_at': row[8]
            })
        
        return flags


# Analysis Functions

async def get_session_analysis(session_uuid: str) -> Dict[str, Any]:
    """Get comprehensive analysis for a session"""
    session = await get_integrity_session(session_uuid)
    if not session:
        return {}
    
    events = await get_session_events(session_uuid)
    flags = await get_session_flags(session_uuid)
    
    # Calculate integrity score
    total_events = len(events)
    flagged_events = len([e for e in events if e['flagged']])
    high_severity_events = len([e for e in events if e['severity'] == 'high'])
    medium_severity_events = len([e for e in events if e['severity'] == 'medium'])
    
    # Simple scoring algorithm
    if total_events == 0:
        integrity_score = 100.0
    else:
        penalty = (high_severity_events * 10) + (medium_severity_events * 5) + (flagged_events * 3)
        integrity_score = max(0, 100 - (penalty / total_events * 10))
    
    # Event type distribution
    event_types = {}
    for event in events:
        event_type = event['event_type']
        if event_type not in event_types:
            event_types[event_type] = 0
        event_types[event_type] += 1
    
    # Severity distribution
    severity_counts = {'low': 0, 'medium': 0, 'high': 0}
    for event in events:
        severity_counts[event['severity']] += 1
    
    return {
        'session': session,
        'integrity_score': round(integrity_score, 2),
        'total_events': total_events,
        'flagged_events': flagged_events,
        'flags_count': len(flags),
        'event_types': event_types,
        'severity_distribution': severity_counts,
        'recent_events': events[:10],  # Last 10 events
        'flags': flags
    }


async def get_cohort_integrity_overview(cohort_id: int) -> Dict[str, Any]:
    """Get integrity overview for a cohort"""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        
        # Get all sessions for cohort
        await cursor.execute(
            f"""SELECT session_uuid FROM {integrity_sessions_table_name} 
                WHERE cohort_id = ?""",
            (cohort_id,)
        )
        session_rows = await cursor.fetchall()
        session_uuids = [row[0] for row in session_rows]
        
        if not session_uuids:
            return {
                'cohort_id': cohort_id,
                'total_sessions': 0,
                'average_integrity_score': 100.0,
                'total_flags': 0,
                'sessions_with_issues': 0
            }
        
        # Get session analyses
        session_analyses = []
        total_score = 0
        sessions_with_issues = 0
        total_flags = 0
        
        for session_uuid in session_uuids:
            analysis = await get_session_analysis(session_uuid)
            if analysis:
                session_analyses.append(analysis)
                total_score += analysis['integrity_score']
                total_flags += analysis['flags_count']
                if analysis['integrity_score'] < 80 or analysis['flags_count'] > 0:
                    sessions_with_issues += 1
        
        average_score = total_score / len(session_analyses) if session_analyses else 100.0
        
        return {
            'cohort_id': cohort_id,
            'total_sessions': len(session_analyses),
            'average_integrity_score': round(average_score, 2),
            'total_flags': total_flags,
            'sessions_with_issues': sessions_with_issues,
            'session_analyses': session_analyses
        }
