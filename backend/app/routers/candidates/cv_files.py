import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Candidate, User
from app.auth import get_current_user, require_admin
from app.services.candidate_service import get_candidate
from app.routers.candidates.helpers import UPLOAD_DIR

router = APIRouter()

MAX_CV_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF-"


@router.get("/{candidate_id}/cv")
def stream_cv(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream the candidate's CV file with proper Content-Type.
    RBAC: only admin or assigned reviewer can view.
    Backward-compatible: still serves previously-uploaded PNG/JPG CVs.
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

    # Determine Content-Type from stored type or file extension
    # Backward-compatible: existing PNG/JPG CVs still get correct MIME type
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
            "Content-Disposition": f'inline; filename="{candidate.cv_file_url}"',
        },
    )


@router.post("/{candidate_id}/cv", status_code=status.HTTP_200_OK)
async def upload_cv(
    candidate_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a CV file for a candidate.
    Only accepts PDF files, max 5 MB, with content validation.
    """
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # ── 1. Validate Content-Type header (first-line check) ──
    if file.content_type != ALLOWED_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only PDF files are accepted.",
        )

    # ── 2. Validate filename extension ──
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file extension. Only .pdf files are accepted.",
        )

    # ── 3. Read file in chunks: validate content, enforce 5 MB limit ──
    total = 0
    first_chunk = b""
    chunks = []
    while True:
        chunk = await file.read(64 * 1024)  # 64 KB chunks
        if not chunk:
            break
        if total == 0:
            first_chunk = chunk
        total += len(chunk)
        if total > MAX_CV_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File exceeds the maximum size of 5 MB.",
            )
        chunks.append(chunk)

    # ── 4. Reject empty files ──
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file. Please upload a valid PDF.",
        )

    # ── 5. Validate PDF magic number in the first bytes ──
    # The magic number should appear at the very start of the file
    if not first_chunk.startswith(PDF_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match PDF format. Expected a valid PDF file.",
        )

    # ── 6. Save the file ──
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_filename = f"cv_{candidate_id}.pdf"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)

    # ── 7. Update candidate record ──
    candidate.cv_file_url = safe_filename
    candidate.cv_content_type = ALLOWED_CONTENT_TYPE
    db.commit()

    return {
        "cv_file_url": safe_filename,
        "cv_content_type": ALLOWED_CONTENT_TYPE,
        "message": "CV uploaded successfully",
    }
