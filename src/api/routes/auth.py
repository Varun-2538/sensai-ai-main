from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from api.db.user import insert_or_return_user
from api.utils.db import get_new_db_connection
from api.models import UserLoginData
from google.oauth2 import id_token
from google.auth.transport import requests
from api.settings import settings
import os
import traceback
import logging

router = APIRouter()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.post("/login")
async def login_or_signup_user(user_data: UserLoginData) -> Dict:
    try:
        logger.info(f"Login attempt for email: {user_data.email}")
        
        # Verify the Google ID token
        try:
            # Get Google Client ID from environment variable
            if not settings.google_client_id:
                logger.error("Google Client ID not configured")
                raise HTTPException(
                    status_code=500, detail="Google Client ID not configured"
                )

            logger.info("Verifying Google ID token...")
            # Verify the token with Google
            id_info = id_token.verify_oauth2_token(
                user_data.id_token, requests.Request(), settings.google_client_id
            )
            logger.info(f"Token verified for email: {id_info.get('email')}")

            # Check that the email in the token matches the provided email
            if id_info["email"] != user_data.email:
                logger.error(f"Email mismatch: token has {id_info['email']}, provided {user_data.email}")
                raise HTTPException(
                    status_code=401, detail="Email in token doesn't match provided email"
                )

        except ValueError as e:
            # Invalid token
            logger.error(f"Invalid authentication token: {str(e)}")
            raise HTTPException(
                status_code=401, detail=f"Invalid authentication token: {str(e)}"
            )

        # If token is valid, proceed with user creation/retrieval
        logger.info("Creating/retrieving user from database...")
        try:
            async with get_new_db_connection() as conn:
                cursor = await conn.cursor()
                user = await insert_or_return_user(
                    cursor,
                    user_data.email,
                    user_data.given_name,
                    user_data.family_name,
                )
                await conn.commit()
                
            logger.info(f"User operation completed. User data: {user}")
            
            # Verify user has required fields
            if not user:
                logger.error("insert_or_return_user returned None")
                raise HTTPException(status_code=500, detail="Failed to create or retrieve user")
            
            if "id" not in user or user["id"] is None:
                logger.error(f"User missing ID field: {user}")
                raise HTTPException(status_code=500, detail="User data missing required ID field")
            
            logger.info(f"Successfully returning user with ID: {user['id']}")
            return user
            
        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
            logger.error(f"Database error traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500, 
                detail=f"Database operation failed: {str(db_error)}"
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error in login_or_signup_user: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Authentication failed: {str(e)}"
        )