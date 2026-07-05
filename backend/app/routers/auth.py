from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, TokenResponse, UserResponse
from app.auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user. Role is ALWAYS hardcoded to 'reviewer' server-side."""
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        role="reviewer",  # Hardcoded — never accept from client
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Login and receive a JWT token."""
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(data={"sub": user.id})
    return TokenResponse(
        access_token=access_token,
        role=user.role,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get the current user's info."""
    return current_user


@router.get("/users/reviewers", response_model=list[UserResponse])
def list_reviewers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all users with reviewer role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list reviewers",
        )
    reviewers = db.query(User).filter(User.role == "reviewer").all()
    return reviewers


@router.post("/admin/seed", response_model=UserResponse)
def seed_admin(db: Session = Depends(get_db)):
    """Seed a default admin user (for demo purposes)."""
    existing = db.query(User).filter(User.email == "admin@techkraft.com").first()
    if existing:
        return existing

    user = User(
        email="admin@techkraft.com",
        hashed_password=hash_password("admin123"),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
