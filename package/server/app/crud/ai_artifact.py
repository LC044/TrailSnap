from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.ai_artifact import AIArtifact
from app.schemas.ai_artifact import AIArtifactUpdate


def get_owned(db: Session, artifact_id: str | UUID, user_id: str | UUID) -> AIArtifact | None:
    return db.query(AIArtifact).filter(AIArtifact.id == artifact_id, AIArtifact.user_id == user_id).first()


def list_owned(db: Session, user_id: str | UUID, skip: int = 0, limit: int = 50) -> list[AIArtifact]:
    return (
        db.query(AIArtifact)
        .filter(AIArtifact.user_id == user_id)
        .order_by(AIArtifact.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update(db: Session, artifact: AIArtifact, values: AIArtifactUpdate) -> AIArtifact:
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(artifact, key, value)
    artifact.version += 1
    db.commit()
    db.refresh(artifact)
    return artifact
