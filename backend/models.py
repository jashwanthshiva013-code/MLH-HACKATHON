"""Pydantic schemas for the structured contribution plan.

The backend NEVER sends arbitrary AI output to the frontend — every plan
is validated against these models first (see backend/app.py).
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class EvidenceLine(BaseModel):
    line: int
    text: str


class RelevantFile(BaseModel):
    path: str
    reason: str
    evidence: List[EvidenceLine] = Field(default_factory=list)
    evidence_summary: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class StartingPoint(BaseModel):
    file: str
    reason: str


class PlanStep(BaseModel):
    text: str
    basis: Literal["confirmed", "suggestion"] = "suggestion"


class Risk(BaseModel):
    area: str
    basis: Literal["confirmed", "suggestion"] = "suggestion"


class IssueUnderstanding(BaseModel):
    title: str
    description: str = ""
    type: Literal["bug", "feature", "enhancement", "documentation", "unknown"] = "unknown"
    explanation: str = ""


class RepoOverview(BaseModel):
    name: str
    language: str = "Unknown"
    files_scanned: int = 0
    folders: List[str] = Field(default_factory=list)
    framework: str = "Not detected"


class TestsPlan(BaseModel):
    existing: List[str] = Field(default_factory=list)
    suggested: List[str] = Field(default_factory=list)
    checklist: List[str] = Field(default_factory=list)
    note: str = ""


class LearningPath(BaseModel):
    topics: List[str] = Field(default_factory=list)
    reading_order: List[str] = Field(default_factory=list)


class ContributionPlan(BaseModel):
    generated_by: str
    issue_understanding: IssueUnderstanding
    repository_overview: RepoOverview
    relevant_files: List[RelevantFile] = Field(default_factory=list)
    flow: List[str] = Field(default_factory=list)
    flow_note: str = ""
    starting_point: Optional[StartingPoint] = None
    steps: List[PlanStep] = Field(default_factory=list)
    tests: TestsPlan = Field(default_factory=TestsPlan)
    risks: List[Risk] = Field(default_factory=list)
    learning: LearningPath = Field(default_factory=LearningPath)
    warnings: List[str] = Field(default_factory=list)
