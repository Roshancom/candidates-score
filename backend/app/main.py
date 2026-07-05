from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base, SessionLocal
from app.models import Candidate, Score, User
from app.routers import auth, candidates, notifications
from app.schemas import CandidateCreate
from app.services.candidate_service import create_candidate

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TechKraft Candidate Assessments",
    description="Internal tool for reviewing and scoring candidates",
    version="1.0.0",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://frontend:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(candidates.router)
app.include_router(notifications.router)


@app.get("/")
def root():
    return {"message": "TechKraft Candidate Assessments API", "version": "1.0.0"}


@app.on_event("startup")
def migrate_and_seed():
    """Run migrations and seed demo data on first startup."""
    db = SessionLocal()
    try:
        # -------- Run schema migrations --------
        from sqlalchemy import inspect as sa_inspect, text
        inspector = sa_inspect(engine)
        
        # Migrate candidates table
        candidate_cols = [c["name"] for c in inspector.get_columns("candidates")]
        if "cv_file_url" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN cv_file_url VARCHAR(500)"))
            print("[migration] Added cv_file_url column")
        if "cv_content_type" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN cv_content_type VARCHAR(100) DEFAULT 'application/pdf'"))
            print("[migration] Added cv_content_type column")
        if "assigned_reviewer_id" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN assigned_reviewer_id INTEGER REFERENCES users(id)"))
            print("[migration] Added assigned_reviewer_id column")
        if "assigned_date" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN assigned_date DATETIME"))
            print("[migration] Added assigned_date column")
        if "is_seed_data" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN is_seed_data INTEGER DEFAULT 0"))
            print("[migration] Added is_seed_data column")
        if "seed_batch_id" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN seed_batch_id VARCHAR(36)"))
            print("[migration] Added seed_batch_id column")
        if "ai_summary" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN ai_summary TEXT"))
            print("[migration] Added ai_summary column")
        if "ai_summary_generated_at" not in candidate_cols:
            db.execute(text("ALTER TABLE candidates ADD COLUMN ai_summary_generated_at DATETIME"))
            print("[migration] Added ai_summary_generated_at column")
        
        # Ensure notifications table exists (created by SQLAlchemy, but might need migration for existing DB)
        try:
            inspector.get_columns("notifications")
        except Exception:
            # Table doesn't exist yet, create it
            from app.models import Notification
            Base.metadata.create_all(bind=engine, tables=[Notification.__table__])
            print("[migration] Created notifications table")
        
        db.commit()

        # If data already exists, assign any unassigned candidates to the reviewer
        if db.query(Candidate).count() > 0:
            reviewer = db.query(User).filter(User.email == "reviewer@techkraft.com").first()
            if reviewer:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                unassigned = db.query(Candidate).filter(
                    Candidate.assigned_reviewer_id.is_(None),
                    Candidate.deleted_at.is_(None),
                ).all()
                for c in unassigned:
                    c.assigned_reviewer_id = reviewer.id
                    c.assigned_date = c.assigned_date or now
                    c.cv_file_url = c.cv_file_url or f"/cv/{c.id}/resume.pdf"
                if unassigned:
                    db.commit()
                    print(f"[seed] Assigned {len(unassigned)} unassigned candidates to reviewer")
            return

        # Seed admin user
        from app.auth import hash_password
        if not db.query(User).filter(User.email == "admin@techkraft.com").first():
            admin = User(
                email="admin@techkraft.com",
                hashed_password=hash_password("admin123"),
                role="admin",
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
        else:
            admin = db.query(User).filter(User.email == "admin@techkraft.com").first()

        # Seed reviewer user
        if not db.query(User).filter(User.email == "reviewer@techkraft.com").first():
            reviewer = User(
                email="reviewer@techkraft.com",
                hashed_password=hash_password("reviewer123"),
                role="reviewer",
            )
            db.add(reviewer)
            db.commit()
            db.refresh(reviewer)
        else:
            reviewer = db.query(User).filter(User.email == "reviewer@techkraft.com").first()

        # Seed candidates
        from datetime import datetime, timezone
        candidates_data = [
            CandidateCreate(
                name="Alice Johnson",
                email="alice@example.com",
                role_applied="Senior Frontend Engineer",
                skills=["React", "TypeScript", "CSS", "GraphQL"],
            ),
            CandidateCreate(
                name="Bob Smith",
                email="bob@example.com",
                role_applied="Backend Engineer",
                skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
            ),
            CandidateCreate(
                name="Carol Davis",
                email="carol@example.com",
                role_applied="Full Stack Developer",
                skills=["JavaScript", "Node.js", "React", "MongoDB"],
            ),
            CandidateCreate(
                name="David Wilson",
                email="david@example.com",
                role_applied="DevOps Engineer",
                skills=["AWS", "Kubernetes", "Terraform", "CI/CD"],
            ),
            CandidateCreate(
                name="Eva Martinez",
                email="eva@example.com",
                role_applied="Data Engineer",
                skills=["Python", "Spark", "SQL", "Airflow"],
            ),
        ]

        created_candidates = []
        for cd in candidates_data:
            candidate = create_candidate(db, cd)
            created_candidates.append(candidate)

        # Assign candidates to the reviewer and set CV files
        now = datetime.now(timezone.utc)
        for i, candidate in enumerate(created_candidates):
            candidate.assigned_reviewer_id = reviewer.id
            candidate.assigned_date = now
            candidate.cv_file_url = f"/cv/{candidate.id}/resume.pdf"

        # Seed some scores
        from app.models import Score
        for i, candidate in enumerate(created_candidates):
            score = Score(
                candidate_id=candidate.id,
                category="Technical Skills",
                score=4.0 + (i % 2),
                reviewer_id=reviewer.id,
                note="Strong technical abilities demonstrated.",
            )
            db.add(score)

            score2 = Score(
                candidate_id=candidate.id,
                category="Communication",
                score=3.5 + (i % 3) * 0.5,
                reviewer_id=reviewer.id,
                note="Good communication skills.",
            )
            db.add(score2)

            # Update status for some
            if i == 0:
                candidate.status = "reviewed"
            elif i == 1:
                candidate.status = "hired"
                from app.models import Score
                admin_score = Score(
                    candidate_id=candidate.id,
                    category="Leadership",
                    score=4.5,
                    reviewer_id=admin.id,
                    note="Strong leadership potential.",
                )
                db.add(admin_score)

        db.commit()

        # Seed notifications for demo purposes
        from app.models import Notification
        from app.services.notification_service import create_notification
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        # Notify reviewer about assigned candidates
        for i, c in enumerate(created_candidates):
            n = create_notification(
                db=db,
                user_id=reviewer.id,
                type="assignment",
                title="New Candidate Assigned",
                message=f"Admin has assigned \"{c.name}\" ({c.role_applied}) to you for review.",
                candidate_id=c.id,
            )
            # Set created_at to be recent
            n.created_at = now - timedelta(hours=i)

        # Notify admin that reviewer submitted first score for Alice
        create_notification(
            db=db,
            user_id=admin.id,
            type="score_submitted",
            title="Review Started: Alice Johnson",
            message=f"Reviewer {reviewer.email} has submitted scores for \"Alice Johnson\" (Senior Frontend Engineer).",
            candidate_id=created_candidates[0].id,
        )

        db.commit()

    finally:
        db.close()
