"""Manage per-repo file ignore patterns."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db

router = APIRouter(prefix="/repos/{repo_owner}/{repo_name}/ignore", tags=["ignore"])


class IgnorePatternIn(BaseModel):
    pattern: str  # e.g. "*.lock", "migrations/*", "vendor/**"


def _full_name(repo_owner: str, repo_name: str) -> str:
    return f"{repo_owner}/{repo_name}"


@router.get("")
async def list_patterns(repo_owner: str, repo_name: str, db: AsyncSession = Depends(get_db)):
    from app.models import IgnorePattern
    rows = await db.execute(
        select(IgnorePattern).where(IgnorePattern.repo_full_name == _full_name(repo_owner, repo_name))
    )
    patterns = rows.scalars().all()
    return [{"id": p.id, "pattern": p.pattern} for p in patterns]


@router.post("", status_code=201)
async def add_pattern(
    repo_owner: str,
    repo_name: str,
    body: IgnorePatternIn,
    db: AsyncSession = Depends(get_db),
):
    from app.models import IgnorePattern
    p = IgnorePattern(repo_full_name=_full_name(repo_owner, repo_name), pattern=body.pattern)
    db.add(p)
    await db.flush()
    return {"id": p.id, "pattern": p.pattern}


@router.delete("/{pattern_id}", status_code=204)
async def delete_pattern(
    repo_owner: str,
    repo_name: str,
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
):
    from app.models import IgnorePattern
    result = await db.execute(
        delete(IgnorePattern).where(
            IgnorePattern.id == pattern_id,
            IgnorePattern.repo_full_name == _full_name(repo_owner, repo_name),
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Pattern not found")
