# Database migration for enhanced assessment features (SQLite compatible)

async def create_assessment_tables(cursor):
    """Create tables for enhanced assessment functionality"""
    
    # MCQ Options table (extends existing questions)
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS mcq_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            option_text TEXT NOT NULL,
            is_correct BOOLEAN DEFAULT FALSE,
            display_order INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        )
    """)
    
    # Test Cases table for coding questions
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS question_test_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            input_data TEXT NOT NULL,
            expected_output TEXT NOT NULL,
            is_hidden BOOLEAN DEFAULT FALSE,
            points INTEGER DEFAULT 1,
            time_limit_seconds INTEGER DEFAULT 5,
            memory_limit_mb INTEGER DEFAULT 128,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        )
    """)
    
    # Assessment Sessions table
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS assessment_sessions (
            id TEXT PRIMARY KEY,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            cohort_id INTEGER,
            integrity_session_id TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            submitted_at DATETIME,
            duration_minutes INTEGER NOT NULL,
            time_remaining_seconds INTEGER,
            status TEXT DEFAULT 'active',
            total_score REAL,
            max_score REAL,
            responses TEXT DEFAULT '{}',
            flagged_questions TEXT DEFAULT '[]',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Question Responses table
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS question_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            response_type TEXT NOT NULL,
            response_data TEXT NOT NULL,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            score REAL,
            max_score REAL,
            auto_graded BOOLEAN DEFAULT FALSE,
            graded_at DATETIME,
            graded_by INTEGER,
            FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            FOREIGN KEY (graded_by) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    
    # Code Execution Results table
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS code_execution_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            response_id INTEGER NOT NULL,
            test_case_id INTEGER NOT NULL,
            passed BOOLEAN NOT NULL,
            actual_output TEXT,
            error_message TEXT,
            execution_time_ms INTEGER,
            memory_used_mb INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (response_id) REFERENCES question_responses(id) ON DELETE CASCADE,
            FOREIGN KEY (test_case_id) REFERENCES question_test_cases(id) ON DELETE CASCADE
        )
    """)
    
    # Assessment Analytics table
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS assessment_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            total_questions INTEGER,
            answered_questions INTEGER,
            correct_answers INTEGER,
            total_score REAL,
            max_score REAL,
            time_spent_minutes INTEGER,
            integrity_score REAL,
            integrity_violations TEXT,
            calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE CASCADE
        )
    """)

async def add_assessment_columns_to_existing_tables(cursor):
    """Add assessment-specific columns to existing tables"""
    
    # SQLite doesn't support adding multiple columns in one statement
    # Add assessment mode columns to tasks table one by one
    try:
        await cursor.execute("ALTER TABLE tasks ADD COLUMN assessment_mode BOOLEAN DEFAULT FALSE")
    except:
        pass  # Column already exists
    
    try:
        await cursor.execute("ALTER TABLE tasks ADD COLUMN duration_minutes INTEGER DEFAULT 60")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE tasks ADD COLUMN attempts_allowed INTEGER DEFAULT 1")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE tasks ADD COLUMN shuffle_questions BOOLEAN DEFAULT FALSE")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE tasks ADD COLUMN show_results BOOLEAN DEFAULT TRUE")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE tasks ADD COLUMN integrity_monitoring BOOLEAN DEFAULT FALSE")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE tasks ADD COLUMN passing_score_percentage INTEGER DEFAULT 60")
    except:
        pass
    
    # Add timing and configuration columns to questions table
    try:
        await cursor.execute("ALTER TABLE questions ADD COLUMN time_limit_minutes INTEGER")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE questions ADD COLUMN points INTEGER DEFAULT 10")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE questions ADD COLUMN question_config TEXT DEFAULT '{}'")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE questions ADD COLUMN allow_multiple_selection BOOLEAN DEFAULT FALSE")
    except:
        pass
    
    try:
        await cursor.execute("ALTER TABLE questions ADD COLUMN shuffle_options BOOLEAN DEFAULT TRUE")
    except:
        pass

async def create_assessment_indexes(cursor):
    """Create indexes for better performance"""
    
    await cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_assessment_sessions_user_task 
        ON assessment_sessions(user_id, task_id)
    """)
    
    await cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_assessment_sessions_status 
        ON assessment_sessions(status)
    """)
    
    await cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_question_responses_session 
        ON question_responses(session_id)
    """)
    
    await cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mcq_options_question 
        ON mcq_options(question_id)
    """)
    
    await cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_cases_question 
        ON question_test_cases(question_id)
    """)

async def migrate_existing_quiz_data(cursor):
    """Migrate existing quiz data to new assessment format"""
    
    # Update existing quiz tasks to assessment mode if they have specific patterns
    await cursor.execute("""
        UPDATE tasks 
        SET assessment_mode = TRUE 
        WHERE type = 'quiz' 
        AND (title ILIKE '%exam%' OR title ILIKE '%test%' OR title ILIKE '%assessment%')
    """)
    
    # Set default points for existing questions
    await cursor.execute("""
        UPDATE questions 
        SET points = 10 
        WHERE points IS NULL
    """)

# Main migration function
async def run_assessment_migration(connection):
    """Run all assessment-related migrations"""
    
    async with connection.cursor() as cursor:
        print("Creating assessment tables...")
        await create_assessment_tables(cursor)
        
        print("Adding assessment columns to existing tables...")
        await add_assessment_columns_to_existing_tables(cursor)
        
        print("Creating assessment indexes...")
        await create_assessment_indexes(cursor)
        
        print("Migrating existing quiz data...")
        await migrate_existing_quiz_data(cursor)
        
        print("Assessment migration completed successfully!")
