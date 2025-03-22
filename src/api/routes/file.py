import traceback
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from api.settings import settings
from api.utils.logging import logger
from api.utils.s3 import generate_s3_uuid, get_audio_upload_s3_key
from api.models import (
    PresignedUrlRequest,
    PresignedUrlResponse,
    S3FetchPresignedUrlRequest,
    S3FetchPresignedUrlResponse,
)

router = APIRouter()


@router.post("/presigned-url/create", response_model=PresignedUrlResponse)
async def get_presigned_url(request: PresignedUrlRequest) -> PresignedUrlResponse:
    try:
        s3_client = boto3.client(
            "s3",
        )

        uuid = generate_s3_uuid()
        key = get_audio_upload_s3_key(uuid)

        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.s3_bucket_name,
                "Key": key,
                "ContentType": request.content_type,
            },
            ExpiresIn=3600,  # URL expires in 1 hour
        )

        return {
            "presigned_url": presigned_url,
            "file_key": key,
            "file_uuid": uuid,
        }

    except ClientError as e:
        logger.error(f"Error generating presigned URL: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate presigned URL")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.post("/presigned-url/get")
async def get_download_presigned_url(
    request: S3FetchPresignedUrlRequest,
) -> S3FetchPresignedUrlResponse:
    try:
        s3_client = boto3.client("s3")

        presigned_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.s3_bucket_name,
                "Key": get_audio_upload_s3_key(request.file_uuid),
            },
            ExpiresIn=3600,  # URL expires in 1 hour
        )

        return {"url": presigned_url}

    except ClientError as e:
        logger.error(f"Error generating download presigned URL: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to generate download presigned URL"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
