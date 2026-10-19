from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SourceFile(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=50000)

    @field_validator('path')
    @classmethod
    def safe_path(cls, value):
        value = value.replace('\\', '/')
        path = PurePosixPath(value)
        if path.is_absolute() or '..' in path.parts or ':' in value:
            raise ValueError('Use a relative repository path.')
        if any(p.startswith('.') and p not in {'.github'} for p in path.parts):
            raise ValueError('Hidden files, including environment files, cannot be indexed.')
        if path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx'}:
            raise ValueError('Credential files cannot be indexed.')
        return value


class IndexRequest(BaseModel):
    project: str = Field(min_length=1, max_length=100, pattern=r'^[\w./-]+$')
    files: list[SourceFile] = Field(min_length=1, max_length=40)


class ReviewRequest(BaseModel):
    project: str = Field(min_length=1, max_length=100, pattern=r'^[\w./-]+$')
    title: str = Field(default='Untitled review', min_length=1, max_length=160)
    diff: str = Field(min_length=1, max_length=50000)


class Finding(BaseModel):
    path: str = Field(max_length=240)
    line: int = Field(ge=1)
    severity: Literal['high', 'medium', 'low']
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=2000)
    suggestion: str = Field(min_length=1, max_length=2000)
    context_ids: list[str] = Field(default_factory=list, max_length=8)


class ModelReview(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    findings: list[Finding] = Field(default_factory=list, max_length=20)


class FeedbackRequest(BaseModel):
    helpful: bool


class PullRequestImport(BaseModel):
    url: str = Field(max_length=500)
