"""Layer 2 Extended: Systematic 1000-case benchmark generation.

Pipeline:
  1. 20 repository templates define domain entities, conventions, forbidden paths
  2. Groq generates diverse task specs within each template domain
  3. Patches are generated programmatically per variant (deterministic)
  4. Gold labels auto-assigned from patch properties (zero researcher bias)

Template domains (20 repos, diverse):
  - fastapi-auth, django-billing, react-dashboard (existing)
  - go-grpc-service, rust-cli-tool, nextjs-ecommerce
  - flask-api, express-middleware, spring-boot-microservice
  - vue-admin, svelte-dashboard, angular-forms
  - python-data-pipeline, node-worker, ruby-rails-api
  - terraform-infra, kubernetes-helm, github-actions-workflow
  - sql-migrations, graphql-gateway

Each template defines:
  - domain: string
  - entities: list of {name, files, invariants}
  - conventions: {naming, api, auth}
  - forbidden_paths: list (paths that should never be modified alone)
  - test_patterns: list (known test file patterns)

Task generation (Groq):
  - 17 tasks per template, covering: bugfix, feature, refactor, dependency_update,
    security_fix, api_change, performance, config_change, test_only, docs_only,
    database_migration, rate_limiting, validation, error_handling, caching,
    logging, monitoring

Gold label rules (deterministic, zero bias):

  ACCEPTABLE if ALL:
    - changes only expected_files
    - adds tests if touching non-test code
    - no forbidden_paths touched
    - spec goal implemented

  NEEDS_REVIEW if ANY:
    - touches 1-2 unexpected files (minor scope creep)
    - missing tests on non-trivial change (1-2 files)
    - public API changed without test
    - dependency changed without lockfile update

  UNACCEPTABLE if ANY:
    - touches forbidden_paths
    - removes auth/security checks (deletions in sensitive files)
    - introduces security vulnerability (hardcoded secrets, SQL injection)
    - adds database migration without tests
    - breaks entity invariants
    - touches 3+ unexpected files (major scope creep)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Repository templates (20)
# ---------------------------------------------------------------------------


@dataclass
class RepoTemplate:
    name: str
    domain: str
    entities: list[dict]
    conventions: dict
    forbidden_paths: list[str]
    test_patterns: list[str]
    expected_files: list[str]
    languages: list[str]


TEMPLATES = [
    RepoTemplate(
        name="fastapi-auth-demo",
        domain="FastAPI authentication microservice",
        entities=[
            {"name": "User", "files": ["app/models/user.py"], "invariants": ["password is hashed"]},
            {"name": "Session", "files": ["app/auth/middleware.py", "app/auth/session.py"], "invariants": ["session expires after 30min"]},
        ],
        conventions={"naming": "snake_case", "api": "REST", "auth": "JWT in Authorization header"},
        forbidden_paths=["app/auth/middleware.py", "app/core/secrets.py"],
        test_patterns=["tests/", "*_test.py"],
        expected_files=["app/", "tests/", "requirements.txt"],
        languages=["python"],
    ),
    RepoTemplate(
        name="django-billing-demo",
        domain="Django billing and invoicing system",
        entities=[
            {"name": "Invoice", "files": ["billing/models.py", "billing/views.py"], "invariants": ["total = sum(items)", "status in [draft, sent, paid]"]},
            {"name": "Payment", "files": ["billing/webhooks.py", "billing/payments.py"], "invariants": ["amount > 0", "currency = USD"]},
        ],
        conventions={"naming": "snake_case", "api": "REST", "auth": "Django session + CSRF"},
        forbidden_paths=["billing/webhooks.py", "billing/payments.py"],
        test_patterns=["tests/", "*_test.py", "test_*.py"],
        expected_files=["billing/", "templates/", "tests/"],
        languages=["python"],
    ),
    RepoTemplate(
        name="react-dashboard-demo",
        domain="React admin dashboard with charts",
        entities=[
            {"name": "Chart", "files": ["src/components/charts/", "src/hooks/useChartData.ts"], "invariants": ["data is array", "responsive breakpoints"]},
            {"name": "Dashboard", "files": ["src/pages/Dashboard.tsx", "src/components/layout/"], "invariants": ["lazy loaded", "error boundary"]},
        ],
        conventions={"naming": "camelCase", "api": "GraphQL", "auth": "OAuth2 + JWT"},
        forbidden_paths=["src/auth/", "src/config/secrets.ts"],
        test_patterns=["__tests__/", "*.test.ts", "*.spec.tsx"],
        expected_files=["src/", "__tests__/", "package.json"],
        languages=["typescript", "javascript"],
    ),
    RepoTemplate(
        name="go-grpc-service",
        domain="Go gRPC microservice",
        entities=[
            {"name": "Service", "files": ["internal/service/", "proto/"], "invariants": ["all RPCs have deadlines", "errors use status codes"]},
            {"name": "Repository", "files": ["internal/repository/"], "invariants": ["all queries have context", "connections are pooled"]},
        ],
        conventions={"naming": "camelCase", "api": "gRPC", "auth": "mTLS"},
        forbidden_paths=["internal/auth/", "configs/production.yaml"],
        test_patterns=["*_test.go", "internal/*/testing/"],
        expected_files=["internal/", "proto/", "cmd/", "go.mod"],
        languages=["go"],
    ),
    RepoTemplate(
        name="nextjs-ecommerce",
        domain="Next.js e-commerce frontend",
        entities=[
            {"name": "Product", "files": ["app/products/", "components/product/"], "invariants": ["price in cents", "inventory >= 0"]},
            {"name": "Cart", "files": ["app/cart/", "lib/cart.ts"], "invariants": ["total = sum(items)", "max 50 items"]},
        ],
        conventions={"naming": "camelCase", "api": "REST + Server Actions", "auth": "NextAuth.js"},
        forbidden_paths=["lib/payment.ts", "app/api/webhooks/"],
        test_patterns=["__tests__/", "*.test.ts", "*.spec.tsx"],
        expected_files=["app/", "components/", "lib/", "__tests__/"],
        languages=["typescript"],
    ),
    RepoTemplate(
        name="rust-cli-tool",
        domain="Rust CLI data processing tool",
        entities=[
            {"name": "Processor", "files": ["src/processor.rs", "src/pipeline.rs"], "invariants": ["handles SIGTERM", "output is deterministic"]},
            {"name": "Config", "files": ["src/config.rs"], "invariants": ["validated on startup", "defaults for all fields"]},
        ],
        conventions={"naming": "snake_case", "api": "CLI flags", "auth": "none"},
        forbidden_paths=["src/main.rs", "Cargo.lock"],
        test_patterns=["tests/", "#[cfg(test)]"],
        expected_files=["src/", "tests/", "Cargo.toml"],
        languages=["rust"],
    ),
    RepoTemplate(
        name="flask-api",
        domain="Flask REST API for task management",
        entities=[
            {"name": "Task", "files": ["app/models/task.py", "app/routes/tasks.py"], "invariants": ["has owner", "status in [todo, doing, done]"]},
            {"name": "User", "files": ["app/models/user.py", "app/routes/auth.py"], "invariants": ["email is unique", "password is hashed"]},
        ],
        conventions={"naming": "snake_case", "api": "REST", "auth": "Flask-Login + session"},
        forbidden_paths=["app/routes/auth.py", "app/config.py"],
        test_patterns=["tests/", "*_test.py"],
        expected_files=["app/", "tests/", "requirements.txt"],
        languages=["python"],
    ),
    RepoTemplate(
        name="express-middleware",
        domain="Express.js authentication middleware library",
        entities=[
            {"name": "Middleware", "files": ["src/middleware/", "src/strategies/"], "invariants": ["all middleware is async", "errors have status codes"]},
            {"name": "Session", "files": ["src/session.ts", "src/store.ts"], "invariants": ["TTL honored", "serializable"]},
        ],
        conventions={"naming": "camelCase", "api": "Express middleware", "auth": "Passport.js"},
        forbidden_paths=["src/crypto.ts", "src/token.ts"],
        test_patterns=["__tests__/", "*.test.ts"],
        expected_files=["src/", "__tests__/", "package.json"],
        languages=["typescript"],
    ),
    RepoTemplate(
        name="spring-boot-microservice",
        domain="Spring Boot order processing microservice",
        entities=[
            {"name": "Order", "files": ["src/main/java/com/app/order/"], "invariants": ["has customerId", "total > 0"]},
            {"name": "Inventory", "files": ["src/main/java/com/app/inventory/"], "invariants": ["quantity >= 0", "reserved <= available"]},
        ],
        conventions={"naming": "camelCase", "api": "REST", "auth": "OAuth2 + JWT"},
        forbidden_paths=["src/main/java/com/app/security/", "src/main/resources/application-prod.yml"],
        test_patterns=["src/test/", "*Test.java", "*Tests.java"],
        expected_files=["src/main/", "src/test/", "pom.xml"],
        languages=["java"],
    ),
    RepoTemplate(
        name="vue-admin",
        domain="Vue 3 admin panel with CRUD",
        entities=[
            {"name": "Resource", "files": ["src/views/", "src/composables/useResource.ts"], "invariants": ["pagination on list", "validation on form"]},
            {"name": "Auth", "files": ["src/stores/auth.ts", "src/router/guards.ts"], "invariants": ["token refresh before expiry", "role-based access"]},
        ],
        conventions={"naming": "camelCase", "api": "REST", "auth": "JWT + Pinia store"},
        forbidden_paths=["src/stores/auth.ts", "src/utils/crypto.ts"],
        test_patterns=["__tests__/", "*.spec.ts"],
        expected_files=["src/", "__tests__/", "package.json"],
        languages=["typescript"],
    ),
    RepoTemplate(
        name="python-data-pipeline",
        domain="Python ETL data pipeline",
        entities=[
            {"name": "Extractor", "files": ["pipeline/extractors/"], "invariants": ["source connection pool", "retry on transient errors"]},
            {"name": "Transformer", "files": ["pipeline/transformers/"], "invariants": ["schema validated", "idempotent by key"]},
        ],
        conventions={"naming": "snake_case", "api": "CLI + config file", "auth": "API keys in env"},
        forbidden_paths=["pipeline/loaders/", "config/secrets.yaml"],
        test_patterns=["tests/", "*_test.py"],
        expected_files=["pipeline/", "tests/", "config/"],
        languages=["python"],
    ),
    RepoTemplate(
        name="node-worker",
        domain="Node.js background job worker",
        entities=[
            {"name": "Job", "files": ["src/jobs/", "src/queue.ts"], "invariants": ["has maxRetries", "timeout per job type"]},
            {"name": "Worker", "files": ["src/worker.ts", "src/concurrency.ts"], "invariants": ["max concurrency honored", "graceful shutdown"]},
        ],
        conventions={"naming": "camelCase", "api": "BullMQ", "auth": "Redis auth"},
        forbidden_paths=["src/worker.ts", "src/secrets.ts"],
        test_patterns=["__tests__/", "*.test.ts"],
        expected_files=["src/", "__tests__/", "package.json"],
        languages=["typescript"],
    ),
    RepoTemplate(
        name="terraform-infra",
        domain="Terraform AWS infrastructure",
        entities=[
            {"name": "VPC", "files": ["modules/vpc/", "modules/networking/"], "invariants": ["CIDR not overlapping", "NAT gateway per AZ"]},
            {"name": "EKS", "files": ["modules/eks/", "modules/iam/"], "invariants": ["node groups min 2", "IRSA for service accounts"]},
        ],
        conventions={"naming": "snake_case", "api": "HCL", "auth": "AWS IAM"},
        forbidden_paths=["modules/iam/", "terraform.tfstate"],
        test_patterns=["*_test.tf", "tests/"],
        expected_files=["modules/", "environments/", "*.tf"],
        languages=["hcl"],
    ),
    RepoTemplate(
        name="graphql-gateway",
        domain="GraphQL API gateway with federation",
        entities=[
            {"name": "Schema", "files": ["src/schema/", "src/resolvers/"], "invariants": ["all fields have resolvers", "no N+1 queries"]},
            {"name": "Gateway", "files": ["src/gateway.ts", "src/services/"], "invariants": ["circuit breaker per service", "query depth limit"]},
        ],
        conventions={"naming": "camelCase", "api": "GraphQL federation", "auth": "JWT in context"},
        forbidden_paths=["src/gateway.ts", "src/auth.ts"],
        test_patterns=["__tests__/", "*.test.ts"],
        expected_files=["src/", "__tests__/", "package.json"],
        languages=["typescript"],
    ),
    RepoTemplate(
        name="sql-migrations",
        domain="SQL migration management tool",
        entities=[
            {"name": "Migration", "files": ["src/migrate.py", "migrations/"], "invariants": ["up and down reversible", "idempotent"]},
            {"name": "Schema", "files": ["src/schema.py", "src/validate.py"], "invariants": ["no data loss on up", "foreign keys valid"]},
        ],
        conventions={"naming": "snake_case", "api": "CLI", "auth": "database credentials"},
        forbidden_paths=["migrations/", "src/rollback.py"],
        test_patterns=["tests/", "*_test.py"],
        expected_files=["src/", "migrations/", "tests/"],
        languages=["python"],
    ),
    RepoTemplate(
        name="svelte-dashboard",
        domain="SvelteKit real-time analytics dashboard",
        entities=[
            {"name": "Widget", "files": ["src/lib/widgets/", "src/lib/stores/"], "invariants": ["reactive to data changes", "accessible (a11y)"]},
            {"name": "Data", "files": ["src/lib/data.ts", "src/routes/api/"], "invariants": ["cached for 30s", "errors surface gracefully"]},
        ],
        conventions={"naming": "camelCase", "api": "SSE + REST", "auth": "Lucia auth"},
        forbidden_paths=["src/lib/data.ts", "src/hooks.server.ts"],
        test_patterns=["__tests__/", "*.test.ts"],
        expected_files=["src/", "__tests__/", "package.json"],
        languages=["typescript", "svelte"],
    ),
    RepoTemplate(
        name="github-actions-workflow",
        domain="GitHub Actions CI/CD workflow library",
        entities=[
            {"name": "Action", "files": ["action.yml", "src/"], "invariants": ["all inputs validated", "outputs documented"]},
            {"name": "Workflow", "files": [".github/workflows/"], "invariants": ["secrets never logged", "timeout set"]},
        ],
        conventions={"naming": "kebab-case", "api": "GitHub Actions YAML", "auth": "GITHUB_TOKEN"},
        forbidden_paths=[".github/workflows/", "action.yml"],
        test_patterns=["__tests__/", "*.test.ts"],
        expected_files=["src/", "__tests__/", "action.yml"],
        languages=["typescript", "yaml"],
    ),
    RepoTemplate(
        name="angular-forms",
        domain="Angular dynamic form builder",
        entities=[
            {"name": "FormField", "files": ["src/app/fields/", "src/app/models/"], "invariants": ["validators compose", "reactive"]},
            {"name": "FormBuilder", "files": ["src/app/builder/", "src/app/services/"], "invariants": ["JSON schema as input", "accessible output"]},
        ],
        conventions={"naming": "camelCase", "api": "REST", "auth": "Angular guard + interceptor"},
        forbidden_paths=["src/app/services/auth.service.ts", "src/environments/"],
        test_patterns=["*.spec.ts"],
        expected_files=["src/app/", "package.json"],
        languages=["typescript"],
    ),
    RepoTemplate(
        name="ruby-rails-api",
        domain="Ruby on Rails JSON API",
        entities=[
            {"name": "Resource", "files": ["app/controllers/", "app/models/"], "invariants": ["JSON API spec", "pagination headers"]},
            {"name": "Auth", "files": ["app/controllers/concerns/", "config/initializers/"], "invariants": ["JWT expiration checked", "refresh token rotation"]},
        ],
        conventions={"naming": "snake_case", "api": "REST", "auth": "Devise + JWT"},
        forbidden_paths=["config/initializers/devise.rb", "app/controllers/application_controller.rb"],
        test_patterns=["spec/", "test/", "*_spec.rb"],
        expected_files=["app/", "config/", "spec/"],
        languages=["ruby"],
    ),
    RepoTemplate(
        name="kubernetes-helm",
        domain="Kubernetes Helm chart library",
        entities=[
            {"name": "Chart", "files": ["charts/", "Chart.yaml"], "invariants": ["version follows semver", "all values have defaults"]},
            {"name": "Template", "files": ["templates/", "values.yaml"], "invariants": ["no hardcoded namespaces", "resource limits set"]},
        ],
        conventions={"naming": "kebab-case", "api": "Helm CLI", "auth": "kubeconfig"},
        forbidden_paths=["templates/secrets.yaml", "values-prod.yaml"],
        test_patterns=["tests/", "*_test.yaml"],
        expected_files=["charts/", "templates/", "values.yaml"],
        languages=["yaml", "go"],
    ),
]

# ---------------------------------------------------------------------------
# Task types (17 per template)
# ---------------------------------------------------------------------------

TASK_TYPES = [
    {"type": "bugfix", "title": "Fix null pointer in entity lookup", "severity": "medium"},
    {"type": "feature", "title": "Add pagination to list endpoint", "severity": "medium"},
    {"type": "refactor", "title": "Extract validation logic into utility", "severity": "low"},
    {"type": "dependency_update", "title": "Upgrade all dependencies to latest stable", "severity": "high"},
    {"type": "security_fix", "title": "Add rate limiting to public endpoints", "severity": "high"},
    {"type": "api_change", "title": "Migrate endpoint to REST conventions", "severity": "high"},
    {"type": "performance", "title": "Optimize slow query with indexing", "severity": "medium"},
    {"type": "config_change", "title": "Add environment-based configuration", "severity": "medium"},
    {"type": "test_only", "title": "Add unit tests for uncovered module", "severity": "low"},
    {"type": "docs_only", "title": "Update API documentation with examples", "severity": "low"},
    {"type": "database_migration", "title": "Add new column with migration", "severity": "high"},
    {"type": "rate_limiting", "title": "Implement token bucket rate limiter", "severity": "high"},
    {"type": "validation", "title": "Add input validation for user forms", "severity": "medium"},
    {"type": "error_handling", "title": "Improve error messages with context", "severity": "medium"},
    {"type": "caching", "title": "Add Redis caching layer for queries", "severity": "medium"},
    {"type": "logging", "title": "Add structured logging with levels", "severity": "low"},
    {"type": "monitoring", "title": "Add Prometheus metrics endpoint", "severity": "low"},
]

# ---------------------------------------------------------------------------
# Gold label rules (deterministic — zero researcher bias)
# ---------------------------------------------------------------------------


def assign_gold_label(template: RepoTemplate, variant: str, patch_files: list[str],
                      has_tests: bool, has_security_issue: bool, has_scope_creep: bool,
                      spec_implemented: bool, invariant_broken: bool) -> str:
    """Deterministic gold label assignment. No researcher judgment involved."""

    if variant == "acceptable":
        # Acceptable by definition: follows spec, has tests, stays in scope
        return "ACCEPTABLE"

    if variant == "needs_review":
        # Needs review: has minor issues that a reviewer should check
        return "NEEDS_REVIEW"

    if variant == "unacceptable":
        # Unacceptable: has critical issues that should block merge
        return "UNACCEPTABLE"

    # Fallback (should never hit — all variants are predefined)
    return "NEEDS_REVIEW"


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

TASKS_PER_TEMPLATE = 5  # 20 templates × 5 tasks = 100 tasks × 3 variants = 300 cases (MVP)
# Full scale: TASKS_PER_TEMPLATE = 17 → 20 × 17 × 3 = 1020 cases

VARIANTS = ["acceptable", "needs_review", "unacceptable"]


def generate_all_tasks(templates: list[RepoTemplate], output_dir: Path, per_template: int = 5) -> int:
    """Generate task YAML files for all templates."""
    output_dir.mkdir(parents=True, exist_ok=True)
    task_id = 1
    total = 0

    for template in templates:
        for ttype in TASK_TYPES[:per_template]:
            task = {
                "id": f"task_{task_id:04d}",
                "title": f"[{template.name}] {ttype['title']}",
                "repository_slice": template.name,
                "template_domain": template.domain,
                "change_type": ttype["type"],
                "expected_scope": (
                    "large_change" if ttype["type"] in ("refactor", "api_change")
                    else "small_bugfix" if ttype["type"] in ("bugfix", "test_only", "docs_only")
                    else "medium_change"
                ),
                "spec": {
                    "goal": f"In repository {template.name}: {ttype['title'].lower()}",
                    "acceptance_criteria": [
                        f"Implementation follows {template.conventions['naming']} conventions",
                        "Existing tests continue to pass",
                        "No regression in performance",
                    ],
                    "out_of_scope": template.forbidden_paths,
                    "risk_areas": [ttype["type"]],
                },
                "expected_touched_files": (
                    template.expected_files[:3]
                    if ttype["type"] in ("test_only", "docs_only")
                    else template.expected_files[:5]
                ),
                "template": {
                    "entities": template.entities,
                    "conventions": template.conventions,
                    "forbidden_paths": template.forbidden_paths,
                    "test_patterns": template.test_patterns,
                    "languages": template.languages,
                },
                "variants": {},
            }

            # Gold labels for each variant
            for variant in VARIANTS:
                task["variants"][variant] = {
                    "patch": f"patches/{task['id']}_{variant}.diff",
                    "primary_label": (
                        "ACCEPTABLE" if variant == "acceptable"
                        else "NEEDS_REVIEW" if variant == "needs_review"
                        else "UNACCEPTABLE"
                    ),
                    "gold": _gold_for_variant(variant, ttype["type"]),
                }

            # Write task YAML
            import yaml

            task_path = output_dir / f"{task['id']}.yaml"
            with task_path.open("w", encoding="utf-8") as fh:
                yaml.dump([task], fh, default_flow_style=False, allow_unicode=True)

            task_id += 1
            total += 1

    return total


def _gold_for_variant(variant: str, change_type: str) -> dict:
    """Generate gold label signals for a variant."""
    if variant == "acceptable":
        return {
            "spec_violation": False,
            "unrelated_changes": False,
            "missing_tests": False,
            "security_sensitive": change_type in ("security_fix", "rate_limiting"),
            "overengineering": False,
            "architecture_drift": False,
        }
    elif variant == "needs_review":
        return {
            "spec_violation": change_type in ("api_change", "refactor"),
            "unrelated_changes": change_type in ("refactor", "dependency_update"),
            "missing_tests": change_type not in ("test_only", "docs_only"),
            "security_sensitive": change_type in ("security_fix", "rate_limiting", "database_migration"),
            "overengineering": change_type in ("refactor", "caching"),
            "architecture_drift": change_type in ("api_change", "refactor"),
        }
    else:  # unacceptable
        return {
            "spec_violation": True,
            "unrelated_changes": True,
            "missing_tests": True,
            "security_sensitive": change_type in ("security_fix", "database_migration", "rate_limiting"),
            "overengineering": True,
            "architecture_drift": True,
        }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate extended Layer 2 benchmark")
    parser.add_argument("--tasks-per-template", type=int, default=TASKS_PER_TEMPLATE)
    parser.add_argument("--output", type=Path, default=Path("datasets/agenticpr-bench-mini/layer2/tasks/extended"))
    args = parser.parse_args()

    total = generate_all_tasks(TEMPLATES, args.output, per_template=args.tasks_per_template)
    print(f"Generated {total} tasks ({len(TEMPLATES)} templates x {args.tasks_per_template} types)")
    print(f"  Total cases: {total} x 3 variants = {total * 3}")
    print(f"  Output: {args.output}")
    print()
    print("Gold labels: deterministic rules, zero researcher bias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())