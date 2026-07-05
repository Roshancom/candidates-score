import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Candidate, User
from app.auth import get_current_user
from app.services.candidate_service import get_candidate
from app.routers.candidates.helpers import UPLOAD_DIR

router = APIRouter()


@router.get("/{candidate_id}/cv")
def stream_cv(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream the candidate's CV file with proper Content-Type.
    RBAC: only admin or assigned reviewer can view.
    """
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # RBAC: only admin or assigned reviewer can view CV
    if current_user.role != "admin" and current_user.id != candidate.assigned_reviewer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this candidate's CV",
        )

    if not candidate.cv_file_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No CV uploaded for this candidate")

    # Normalize cv_file_url: strip leading slashes to avoid os.path.join ignoring UPLOAD_DIR
    normalized_path = candidate.cv_file_url.lstrip("/")
    file_path = os.path.join(UPLOAD_DIR, normalized_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV file not found on disk")

    # Determine Content-Type from the file extension or stored type
    content_type = candidate.cv_content_type or "application/pdf"
    if not content_type or content_type == "application/octet-stream":
        ext = os.path.splitext(candidate.cv_file_url)[1].lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        content_type = mime_map.get(ext, "application/octet-stream")

    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=candidate.cv_file_url,
        headers={
            "Content-Disposition": f"inline; filename=\"{candidate.cv_file_url}\"",
        },
    )


@router.post("/{candidate_id}/cv", status_code=status.HTTP_200_OK)
async def upload_cv(
    candidate_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a CV file for a candidate.
    Only accepts .pdf, .png, .jpg files.
    """
    # Only admins can upload CVs
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can upload CVs",
        )

    candidate = get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # Validate file type
    allowed_types = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_types.values())}",
        )

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Generate a safe filename
    ext = allowed_types[file.content_type]
    safe_filename = f"cv_{candidate_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    # Save the file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Update candidate record
    candidate.cv_file_url = safe_filename
    candidate.cv_content_type = file.content_type
    db.commit()

    return {
        "cv_file_url": safe_filename,
        "cv_content_type": file.content_type,
        "message": "CV uploaded successfully",
    }
