#!/usr/bin/env python3
"""
Quick script to run assessment database migration
"""

import asyncio
import os
import sys

# Add src to path so we can import api modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from api.utils.db import get_new_db_connection
from api.db.assessment_migration import (
    create_assessment_tables,
    add_assessment_columns_to_existing_tables,
    create_assessment_indexes
)

async def run_migration():
    """Run the assessment migration"""
    print("Starting assessment database migration...")
    
    try:
        async with get_new_db_connection() as connection:
            async with connection.cursor() as cursor:
                print("Creating assessment tables...")
                await create_assessment_tables(cursor)
                
                print("Adding assessment columns to existing tables...")
                await add_assessment_columns_to_existing_tables(cursor)
                
                print("Creating assessment indexes...")
                await create_assessment_indexes(cursor)
                
                await connection.commit()
                print("✅ Assessment migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(run_migration())
