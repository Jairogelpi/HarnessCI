from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HarnessCIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Decision(StrEnum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCK = "BLOCK"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


class ChangeType(StrEnum):
    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    TEST_ONLY = "test-only"
    DOCS_ONLY = "docs-only"
    SECURITY_SENSITIVE = "security-sensitive"
    DEPENDENCY_UPDATE = "dependency-update"
    DATABASE_CHANGE = "database-change"
    UNKNOWN = "unknown"


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(StrEnum):
    SPEC = "spec"
    DIFF = "diff"
    TESTS = "tests"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    TELEMETRY = "telemetry"
    CONFIG = "config"
    REPORT = "report"


class ExpectedScope(StrEnum):
    SMALL_BUGFIX = "small_bugfix"
    MEDIUM_CHANGE = "medium_change"
    LARGE_CHANGE = "large_change"
    UNKNOWN = "unknown"


class SpecModel(HarnessCIModel):
    source_path: str | None = None
    goal: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    risk_areas: list[str] = Field(default_factory=list)
    expected_scope: ExpectedScope = ExpectedScope.UNKNOWN
    usable: bool = False

    @model_validator(mode="after")
    def derive_usability(self) -> "SpecModel":
        self.usable = bool(self.goal.strip() or self.acceptance_criteria)
        return self


class DiffFileChange(HarnessCIModel):
    path: str
    old_path: str | None = None
    status: str
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = Field(default=0, ge=0)
    is_test: bool = False
    is_docs: bool = False
    is_config: bool = False
    is_dependency: bool = False
    is_database: bool = False
    is_sensitive: bool = False


class DiffFeatures(HarnessCIModel):
    files_changed: int = Field(ge=0)
    lines_added: int = Field(ge=0)
    lines_deleted: int = Field(ge=0)
    total_churn: int = Field(ge=0)
    test_files_changed: int = Field(ge=0)
    config_files_changed: int = Field(ge=0)
    dependency_changes: int = Field(ge=0)
    database_migration_added: bool
    public_api_changed: bool
    sensitive_files_touched: list[str] = Field(default_factory=list)
    change_type: ChangeType = ChangeType.UNKNOWN
    files: list[DiffFileChange] = Field(default_factory=list)


class TestSignals(HarnessCIModel):
    tests_passed: bool | None = None
    tests_failed: bool | None = None
    new_tests_added: bool = False
    changed_tests: int = Field(default=0, ge=0)
    coverage_delta: float | None = None
    acceptance_criteria_covered: int | None = Field(default=None, ge=0)
    mutation_signal: str | None = None


class TelemetrySummary(HarnessCIModel):
    available: bool = False
    agent_name: str | None = None
    model_name: str | None = None
    harness_type: str | None = None
    tool_calls: int | None = Field(default=None, ge=0)
    test_runs: int | None = Field(default=None, ge=0)
    failed_test_runs: int | None = Field(default=None, ge=0)
    edit_attempts: int | None = Field(default=None, ge=0)
    retries: int | None = Field(default=None, ge=0)
    tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    error_count: int | None = Field(default=None, ge=0)
    cost_estimate: float | None = Field(default=None, ge=0)


class ScoreBreakdown(HarnessCIModel):
    spec_compliance_score: int = Field(ge=0, le=100)
    diff_minimality_score: int = Field(ge=0, le=100)
    test_adequacy_score: int = Field(ge=0, le=100)
    security_risk_score: int = Field(ge=0, le=100)
    architecture_drift_score: int = Field(ge=0, le=100)
    harness_efficiency_score: int = Field(ge=0, le=100)
    overall_agentic_risk: int = Field(ge=0, le=100)


class AuditFinding(HarnessCIModel):
    severity: FindingSeverity
    category: FindingCategory
    message: str
    evidence: str | None = None
    explanation: str | None = None  # NL explanation from Groq


class AuditReport(HarnessCIModel):
    decision: Decision
    overall_agentic_risk: int = Field(ge=0, le=100)
    scores: ScoreBreakdown
    spec: SpecModel
    diff: DiffFeatures
    test_signals: TestSignals = Field(default_factory=TestSignals)
    telemetry: TelemetrySummary = Field(default_factory=TelemetrySummary)
    findings: list[AuditFinding] = Field(default_factory=list)
    recommendation: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    # New: NL generation
    nl_summary: dict[str, str] | None = None  # {summary, risks, tests, security}
    bug_pattern_matches: int | None = None  # Count of generic bug patterns detected
    session_autopsy: dict | None = None  # Human-readable telemetry interpretation
