"""Template catalog tests (Initiative C). No Docker, no API key, no network."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.templates import templates_router
from app.templates import get_template, list_packs, list_templates


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(templates_router)
    return TestClient(app)


# --- registry units ------------------------------------------------------


def test_packs_cover_legal_finance_general():
    domains = {p.domain for p in list_packs()}
    assert {"legal", "finance", "general"} <= domains


def test_templates_have_required_fields_and_unique_ids():
    templates = list_templates()
    assert len(templates) >= 6
    ids = [t.id for t in templates]
    assert len(ids) == len(set(ids))  # globally unique (registry also enforces this)
    for t in templates:
        assert t.id and t.title and t.description
        assert len(t.query) > 20  # a real, runnable prompt
        assert t.domain in {"legal", "finance", "general"}


def test_domain_filter():
    legal = list_templates(domain="legal")
    assert legal and all(t.domain == "legal" for t in legal)


def test_get_template_by_id():
    assert get_template("legal-contract-extract") is not None
    assert get_template("does-not-exist") is None


# --- endpoint integration ------------------------------------------------


def test_list_endpoint_and_filter():
    client = _client()
    res = client.get("/v1/templates")
    assert res.status_code == 200
    body = res.json()
    assert len(body) >= 6
    assert {"id", "title", "query", "domain", "pack", "tags"} <= set(body[0])

    finance = client.get("/v1/templates", params={"domain": "finance"}).json()
    assert finance and all(t["domain"] == "finance" for t in finance)


def test_packs_endpoint():
    res = _client().get("/v1/templates/packs")
    assert res.status_code == 200
    packs = res.json()
    assert {"legal", "finance", "general"} <= {p["id"] for p in packs}
    assert all(p["template_ids"] for p in packs)


def test_single_template_and_404():
    client = _client()
    ok = client.get("/v1/templates/finance-equity-metrics")
    assert ok.status_code == 200
    assert ok.json()["domain"] == "finance"

    assert client.get("/v1/templates/nope").status_code == 404
