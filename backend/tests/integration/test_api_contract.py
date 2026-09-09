"""The API surface: what is registered, what it answers, and what it may import.

Everything here reads the *live* FastAPI application rather than the
documentation, because a route table and a document that disagree is exactly
the situation these tests exist to prevent.

No database is involved. None of the Delivery Phase 2 endpoints touches one.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import API_PREFIX, API_V1_PREFIX, app

BACKEND = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND / "app"

#: The product API, exactly. A route appearing here that is not in the
#: application - or the reverse - fails the first test below.
EXPECTED_PRODUCT_ROUTES = {
    ("POST", "/api/v1/mdr/upload"),
    ("POST", "/api/v1/mdr/{mdr_id}/extract"),
    ("POST", "/api/v1/mdr/{mdr_id}/automate"),
    ("GET", "/api/v1/mdr/{mdr_id}/summary"),
    ("GET", "/api/v1/mdr/{mdr_id}/download"),
}

EXPECTED_OPERATIONAL_ROUTES = {("GET", "/api/health")}

#: FastAPI's own documentation routes, which are not part of the contract.
_DOC_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def registered_routes() -> set[tuple[str, str]]:
    """Every (method, path) the application actually serves."""
    found = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path in _DOC_PATHS:
            continue
        for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
            found.add((method, path))
    return found


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestRouteTable:

    def test_the_application_serves_exactly_the_expected_routes(self):
        assert registered_routes() == (
            EXPECTED_PRODUCT_ROUTES | EXPECTED_OPERATIONAL_ROUTES)

    def test_health_is_not_versioned(self):
        """Operational endpoints must not follow the product API's version."""
        assert ("GET", "/api/health") in registered_routes()
        assert not [p for _, p in registered_routes()
                    if p.startswith("/api/v1/health")]

    def test_the_old_unversioned_mdr_route_is_gone(self):
        """`GET /api/mdr/summary` was removed, not left beside the v1 routes."""
        unversioned = [p for _, p in registered_routes()
                       if p.startswith("/api/mdr")]
        assert unversioned == []

    def test_every_product_route_is_under_v1(self):
        product = {p for _, p in registered_routes()
                   if "mdr" in p or "submission" in p}
        assert product and all(p.startswith(API_V1_PREFIX) for p in product)

    def test_the_prefixes_are_what_the_policy_says(self):
        assert API_PREFIX == "/api"
        assert API_V1_PREFIX == "/api/v1"

    def test_no_v2_exists(self):
        assert not [p for _, p in registered_routes() if "/v2/" in p]

    def test_the_workflow_is_legible_from_the_paths_alone(self):
        """upload -> extract -> automate -> summary -> download."""
        paths = {p for _, p in EXPECTED_PRODUCT_ROUTES}
        for step in ("upload", "extract", "automate", "summary", "download"):
            assert any(p.endswith(step) for p in paths), step


class TestResponses:

    def test_health_answers(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_upload_reports_not_implemented(self, client):
        response = client.post(
            "/api/v1/mdr/upload",
            data={"plant_id": str(uuid.uuid4())},
            files={"mdr_file": ("log.xlsx", b"not a real workbook")})
        assert response.status_code == 501
        assert "not implemented" in response.json()["detail"].lower()

    def test_upload_still_validates_its_request(self, client):
        """The multipart contract is real, not decorative."""
        assert client.post("/api/v1/mdr/upload").status_code == 422

    @pytest.mark.parametrize("method,suffix", [
        ("post", "extract"), ("post", "automate"),
        ("get", "summary"), ("get", "download"),
    ])
    def test_the_workflow_endpoints_report_not_implemented(self, client, method,
                                                           suffix):
        response = getattr(client, method)(
            f"/api/v1/mdr/{uuid.uuid4()}/{suffix}")
        assert response.status_code == 501

    def test_no_endpoint_fabricates_a_result(self, client):
        """A 501 body carries an explanation, never processing output."""
        body = client.get(f"/api/v1/mdr/{uuid.uuid4()}/summary").json()
        assert set(body) == {"detail"}

    def test_a_malformed_id_is_rejected_before_the_handler(self, client):
        assert client.get("/api/v1/mdr/not-a-uuid/summary").status_code == 422


class TestOpenApiContract:

    def test_the_contract_documents_the_response_shapes(self, client):
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        assert {"UploadResponse", "ExtractResponse", "AutomateResponse",
                "SummaryResponse", "RuleSetRef"} <= set(schemas)

    def test_a_summary_declares_its_rule_set(self, client):
        """The field that makes a historical result explainable."""
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        assert "rule_set" in schemas["SummaryResponse"]["properties"]


class TestLayering:
    """Routes stay thin, and versioning stays at the boundary."""

    ROUTE_MODULES = sorted((APP_DIR / "api" / "routes").glob("*.py"))

    #: What a route module may never import. SQLAlchemy would put SQL in a
    #: route; openpyxl would put spreadsheet parsing in one; the engine
    #: packages would put MDR rules in one.
    FORBIDDEN = {"sqlalchemy", "psycopg", "alembic", "openpyxl"}

    @staticmethod
    def imported_modules(path: Path) -> set[str]:
        # utf-8-sig: some sources in this repository carry a BOM, which
        # `ast.parse` rejects as a non-printable character.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(node.module.split(".")[0])
        return found

    @pytest.mark.parametrize("path", ROUTE_MODULES, ids=lambda p: p.name)
    def test_a_route_module_imports_no_infrastructure(self, path):
        assert not self.imported_modules(path) & self.FORBIDDEN

    @pytest.mark.parametrize("path", ROUTE_MODULES, ids=lambda p: p.name)
    def test_a_route_module_contains_no_sql(self, path):
        source = path.read_text(encoding="utf-8-sig").upper()
        for fragment in ("SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM"):
            assert fragment not in source, f"{path.name} contains {fragment!r}"

    @pytest.mark.parametrize("path", ROUTE_MODULES, ids=lambda p: p.name)
    def test_a_route_module_holds_no_mdr_rule(self, path):
        """No route may reach into the engine; rules live below the service."""
        imports = {n.module for n in ast.walk(
            ast.parse(path.read_text(encoding="utf-8-sig")))
            if isinstance(n, ast.ImportFrom) and n.module}
        assert not [m for m in imports if m.startswith("engine")
                    or ".engine" in m]

    @pytest.mark.parametrize("layer", ["domain", "engine"])
    def test_the_business_layers_do_not_know_sqlalchemy_exists(self, layer):
        """PostgreSQL was added around the engine, not into it."""
        offenders = [
            path.relative_to(BACKEND)
            for path in (APP_DIR / layer).rglob("*.py")
            if self.imported_modules(path) & {"sqlalchemy", "psycopg", "alembic"}
        ]
        assert offenders == []

    @pytest.mark.parametrize("layer", ["services", "domain", "engine",
                                       "infrastructure"])
    def test_no_internal_layer_is_versioned(self, layer):
        """`v1` is a URL prefix. It is not a package name anywhere."""
        versioned = [d.relative_to(BACKEND) for d in (APP_DIR / layer).rglob("*")
                     if d.is_dir() and d.name in {"v1", "v2"}]
        assert versioned == []
