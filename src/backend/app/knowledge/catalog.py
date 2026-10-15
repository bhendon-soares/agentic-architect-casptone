"""Synchronize local demo source metadata without storing document contents."""

import os
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import KnowledgeSource
from app.runtime.policy import CATEGORIES, redact


def knowledge_base() -> Path:
    configured = os.getenv("KNOWLEDGE_BASE_PATH")
    backend = Path(__file__).resolve().parents[2]
    return (
        (backend / configured) if configured else backend.parents[1] / "knowledge"
    ).resolve()


def sync_catalog(db: Session) -> None:
    base = knowledge_base()
    for category in CATEGORIES:
        source = (base / f"{category}.md").resolve()
        if not source.is_relative_to(base) or not source.is_file():
            continue
        content = source.read_text(encoding="utf-8")
        if (
            not content.startswith("# ")
            or "Aprovacao: somente para demo" not in content
        ):
            continue
        path = f"knowledge/{category}.md"
        record = db.scalar(select(KnowledgeSource).where(KnowledgeSource.path == path))
        digest = sha256(content.encode()).hexdigest()
        safe_title = redact(content.splitlines()[0][2:].strip())
        if record is None:
            record = KnowledgeSource(
                path=path,
                title=safe_title,
                internal_category=category,
                content_hash=digest,
            )
            db.add(record)
        else:
            record.title = safe_title
            if record.content_hash != digest:
                record.content_hash = digest
                record.approved = False
    db.commit()
