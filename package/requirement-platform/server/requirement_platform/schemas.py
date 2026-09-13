from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class GitHubIdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    github_user_id: int
    login: str
    avatar_url: str | None
    profile_url: str | None
    email: str | None
    linked_at: datetime
    last_login_at: datetime | None


class RoleUpdate(BaseModel):
    role: Literal["viewer", "admin"]


class GitHubIssueLinkInput(BaseModel):
    issue_number: int = Field(ge=1)


class ReasonInput(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class AgentTokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    scopes: list[Literal[
        "requirements:read", "requirements:write", "requirements:review",
        "versions:read", "versions:write", "github:write",
        "specs:read", "tasks:write", "tasks:claim", "runs:write", "artifacts:write", "tests:submit"
    ]] = Field(min_length=1)
    expires_in_days: int | None = Field(default=90, ge=1, le=365)
    project_key: Literal["trailsnap"] = "trailsnap"
    agent_role: Literal["coding", "testing", "review"] | None = None
    task_id: str | None = None


class RequirementCreate(BaseModel):
    type: Literal["bug", "improvement", "feature"]
    title: str = Field(min_length=4, max_length=160)
    description: str = Field(min_length=10, max_length=8000)
    log_text: str | None = Field(default=None, max_length=20000)
    current_behavior: str | None = Field(default=None, max_length=3000)
    expected_behavior: str | None = Field(default=None, max_length=3000)
    steps_to_reproduce: str | None = Field(default=None, max_length=4000)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    product_version: str | None = Field(default=None, max_length=50)
    environment: dict[str, Any] = Field(default_factory=dict)
    visibility: Literal["public", "private"] = "public"
    submitter_name: str | None = Field(default=None, max_length=50)
    submitter_contact: str | None = Field(default=None, max_length=255)
    ai_clarification_answers: dict[str, str] = Field(default_factory=dict)


class RequirementUpdate(BaseModel):
    type: Literal["bug", "improvement", "feature"] | None = None
    title: str | None = Field(default=None, min_length=4, max_length=160)
    description: str | None = Field(default=None, min_length=10, max_length=8000)
    log_text: str | None = Field(default=None, max_length=20000)
    current_behavior: str | None = Field(default=None, max_length=3000)
    expected_behavior: str | None = Field(default=None, max_length=3000)
    steps_to_reproduce: str | None = Field(default=None, max_length=4000)
    severity: Literal["low", "medium", "high", "critical"] | None = None
    product_version: str | None = Field(default=None, max_length=50)
    visibility: Literal["public", "private"] | None = None
    environment: dict[str, Any] | None = None


class TriageQuestion(BaseModel):
    question_id: str = Field(min_length=1, max_length=40)
    target_field: str | None = Field(default=None, max_length=80)
    question: str = Field(min_length=2, max_length=1000)
    rationale: str = Field(min_length=2, max_length=1000)
    blocking: bool = True
    suggested_options: list[str] = Field(default_factory=list, max_length=6)


class TriageReportV2(BaseModel):
    schema_version: Literal[2] = 2
    requirement_revision: int = Field(ge=1)
    context_bundle_id: str | None = None
    problem_summary: str = Field(min_length=2, max_length=2000)
    category: Literal["bug", "improvement", "feature"]
    confirmed_facts: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    completeness_items: list[dict[str, Any]] = Field(default_factory=list)
    blocking_questions: list[TriageQuestion] = Field(default_factory=list, max_length=3)
    nonblocking_questions: list[TriageQuestion] = Field(default_factory=list, max_length=3)
    duplicate_candidates: list[dict[str, Any]] = Field(default_factory=list)
    value_assessment: dict[str, Any] = Field(default_factory=dict)
    feasibility: str = Field(default="unknown", max_length=100)
    affected_components: list[str] = Field(default_factory=list)
    risks: list[dict[str, Any] | str] = Field(default_factory=list)
    effort_range: str = Field(default="unknown", max_length=100)
    recommended_disposition: Literal["clarify", "pending_review", "possible_duplicate", "defer", "reject"]
    acceptance_draft: list[str] = Field(default_factory=list)
    model: str | None = None
    prompt_version: str = "triage-v2"
    knowledge_revision: str | None = None
    generated_at: datetime
    fallback_reason: str | None = None


class PreflightTriageInput(RequirementCreate):
    answers: dict[str, str] = Field(default_factory=dict)


class AIConnectionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    provider: Literal["openai_compatible"] = "openai_compatible"
    api_base: str = Field(min_length=8, max_length=500)
    api_key: str = Field(default="", max_length=4000)
    enabled: bool = True
    timeout_seconds: int = Field(default=45, ge=3, le=180)
    priority: int = Field(default=100, ge=0, le=10000)

    @model_validator(mode="after")
    def validate_api_base(self):
        if not self.api_base.startswith(("http://", "https://")):
            raise ValueError("api_base must use http or https")
        return self


class AIConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    api_base: str | None = Field(default=None, min_length=8, max_length=500)
    api_key: str | None = Field(default=None, max_length=4000)
    clear_api_key: bool = False
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=3, le=180)
    priority: int | None = Field(default=None, ge=0, le=10000)

    @model_validator(mode="after")
    def validate_api_base(self):
        if self.api_base is not None and not self.api_base.startswith(("http://", "https://")):
            raise ValueError("api_base must use http or https")
        return self


class AIModelCreate(BaseModel):
    model_name: str = Field(min_length=1, max_length=160)
    display_name: str = Field(default="", max_length=160)
    enabled: bool = True
    supports_json_mode: bool = True
    context_window: int | None = Field(default=None, ge=1024, le=10_000_000)
    reasoning_levels: list[Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]] = Field(
        default_factory=lambda: ["none", "low", "medium", "high"], min_length=1
    )


class AIModelUpdate(BaseModel):
    model_name: str | None = Field(default=None, min_length=1, max_length=160)
    display_name: str | None = Field(default=None, max_length=160)
    enabled: bool | None = None
    supports_json_mode: bool | None = None
    context_window: int | None = Field(default=None, ge=1024, le=10_000_000)
    reasoning_levels: list[Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]] | None = Field(
        default=None, min_length=1
    )


AITaskType = Literal["preflight_triage", "requirement_triage", "spec_drafting", "coding", "testing", "review"]


class AITaskRouteUpdate(BaseModel):
    enabled: bool = True
    model_ids: list[str] = Field(default_factory=list, max_length=10)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] = "none"

    @model_validator(mode="after")
    def unique_models(self):
        if len(self.model_ids) != len(set(self.model_ids)):
            raise ValueError("model_ids must be unique")
        return self


class AIConnectionTestInput(BaseModel):
    model_id: str | None = None


class ClarificationAnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    expected_state_version: int = Field(ge=1)


class SummaryCorrectionInput(BaseModel):
    summary: str = Field(min_length=4, max_length=2000)
    expected_state_version: int = Field(ge=1)


class AcceptanceCriterionInput(BaseModel):
    id: str = Field(min_length=1, max_length=30, pattern=r"^AC-[A-Za-z0-9_-]+$")
    given: str = Field(min_length=1, max_length=2000)
    when: str = Field(min_length=1, max_length=2000)
    then: str = Field(min_length=1, max_length=3000)
    required: bool = True
    verification: str = Field(min_length=1, max_length=50)
    dataset: str | None = Field(default=None, max_length=120)


class RequirementSpecContent(BaseModel):
    problem: str = Field(min_length=4, max_length=6000)
    user_scenario: str = Field(min_length=4, max_length=6000)
    goal: str = Field(min_length=4, max_length=4000)
    confirmed_facts: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    in_scope: list[str] = Field(min_length=1)
    out_of_scope: list[str] = Field(default_factory=list)
    behavior_rules: list[str] = Field(default_factory=list)
    acceptance: list[AcceptanceCriterionInput] = Field(min_length=1)
    test_data_requirements: list[str] = Field(default_factory=list)
    environment_requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    release_requirements: list[str] = Field(default_factory=list)
    rollback_requirements: list[str] = Field(default_factory=list)
    blocking_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    repository: Literal["LC044/TrailSnap"] = "LC044/TrailSnap"
    target_branch: Literal["master"] = "master"
    base_sha: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40}$")

    @model_validator(mode="after")
    def unique_acceptance_ids(self):
        ids = [item.id for item in self.acceptance]
        if len(ids) != len(set(ids)):
            raise ValueError("验收标准 ID 不能重复")
        return self


class RequirementSpecCreate(BaseModel):
    content: RequirementSpecContent
    expected_requirement_state_version: int = Field(ge=1)


class RequirementSpecUpdate(BaseModel):
    content: RequirementSpecContent
    expected_state_version: int = Field(ge=1)


class SpecApproveInput(BaseModel):
    expected_state_version: int = Field(ge=1)
    manual_base_sha: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40}$")


class DeliveryTaskCreate(BaseModel):
    spec_id: str
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    budget: dict[str, Any] = Field(default_factory=dict)
    dependency_ids: list[str] = Field(default_factory=list)


class AgentClaimInput(BaseModel):
    runner_name: str = Field(min_length=1, max_length=120)
    provider: Literal["codex", "claude"]
    model: str | None = Field(default=None, max_length=100)
    role: Literal["coding"] = "coding"


class RunWriteInput(BaseModel):
    attempt_id: str
    lease_token: str
    expected_state_version: int = Field(ge=1)


class RunHeartbeatInput(RunWriteInput):
    session_reference: str | None = Field(default=None, max_length=255)


class ImplementationPlanInput(RunWriteInput):
    goal_summary: str = Field(min_length=4, max_length=4000)
    scope_summary: str = Field(min_length=4, max_length=4000)
    acceptance_plan: dict[str, str] = Field(min_length=1)
    affected_modules: list[str] = Field(default_factory=list)
    migrations: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list, max_length=10)
    out_of_scope: list[str] = Field(default_factory=list)


class RunQuestionInput(RunWriteInput):
    question: str = Field(min_length=2, max_length=4000)
    blocking: bool = True


class RunQuestionAnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    expected_run_state_version: int = Field(ge=1)
    requires_spec_revision: bool = False


class RunResultInput(RunWriteInput):
    status: Literal["succeeded", "failed", "cancelled"]
    summary: str = Field(min_length=1, max_length=8000)
    changed_files: list[str] = Field(default_factory=list)
    acceptance_coverage: dict[str, Any] = Field(default_factory=dict)
    self_test_results: list[dict[str, Any]] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    head_sha: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40}$")
    usage: dict[str, Any] = Field(default_factory=dict)
    exit_reason: str | None = Field(default=None, max_length=4000)


class ArtifactInput(RunWriteInput):
    kind: str = Field(min_length=1, max_length=40)
    uri: str = Field(min_length=1, max_length=1000)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    mime_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=0)
    access_level: Literal["private", "manager", "public"] = "private"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PullRequestLinkInput(BaseModel):
    pull_request_number: int = Field(ge=1)
    url: str = Field(min_length=8, max_length=500)
    head_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    base_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    covered_acceptance_ids: list[str] = Field(default_factory=list)
    expected_state_version: int = Field(ge=1)


class ReviewInput(BaseModel):
    action: Literal["candidate", "needs_information", "rejected", "deferred", "duplicate", "close"]
    reason: str = Field(min_length=2, max_length=2000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    duplicate_of_id: str | None = None


class RequirementStatusInput(BaseModel):
    status: Literal[
        "submitted", "triaging", "pending_review", "needs_information", "candidate", "scheduled",
        "accepted", "developing", "testing", "release_ready", "merged", "released", "deferred", "rejected", "duplicate",
        "withdrawn", "closed",
    ]
    reason: str = Field(min_length=2, max_length=2000)


class DeliveryStatusInput(BaseModel):
    status: Literal["not_started", "developing", "pr_open", "testing", "completed", "blocked", "removed"]


class BatchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    version_name: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    batch_type: Literal["fix", "feature", "major", "hotfix"] = "feature"
    goal: str = Field(min_length=4, max_length=4000)
    target_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    max_risk_level: Literal["low", "medium", "high", "critical"] = "high"


class BatchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    version_name: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    batch_type: Literal["fix", "feature", "major", "hotfix"] | None = None
    goal: str | None = Field(default=None, min_length=4, max_length=4000)
    target_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    max_risk_level: Literal["low", "medium", "high", "critical"] | None = None


class BatchItemInput(BaseModel):
    requirement_id: str
    priority_order: int = Field(default=0, ge=0, le=10000)


class BatchStatusInput(BaseModel):
    status: Literal["planning", "candidate_selection", "scope_locked", "developing", "testing", "release_ready", "published", "completed", "blocked", "paused", "cancelled"]
    reason: str = Field(min_length=2, max_length=2000)


class RequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    public_number: int | None
    type: str
    title: str
    description: str
    log_text: str | None
    current_behavior: str | None
    expected_behavior: str | None
    steps_to_reproduce: str | None
    severity: str
    product_version: str | None
    environment: dict[str, Any]
    visibility: str
    status: str
    priority: str
    risk_level: str
    review_reason: str | None
    duplicate_of_id: str | None
    github_issue_number: int | None
    github_issue_url: str | None
    github_state: str | None
    github_pull_requests: list[dict[str, Any]]
    source: str
    created_by: str | None
    submitter_name: str | None
    submitter_contact: str | None
    created_at: datetime
    updated_at: datetime
    version: int
    content_revision: int
    state_version: int
    confirmed_summary: str | None
    deleted_at: datetime | None
    deleted_by: str | None
    delete_reason: str | None


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    version_name: str
    batch_type: str
    goal: str
    status: str
    target_date: str | None
    max_risk_level: str
    scope_summary: str | None
    github_milestone_number: int | None
    github_milestone_url: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None
