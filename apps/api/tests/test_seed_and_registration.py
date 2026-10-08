"""Regression: the pipeline must evaluate identically whether entered via HTTP or via scripts (seed) — G12 smoke finding."""

import os
import sys

import pytest
from sqlalchemy import select

from app.db import get_sessionmaker
from app.models.case import CustomsCase
from app.models.goods import GoodsItem
from app.models.issue import Issue
from app.models.knowledge import KnowledgeDataset


def test_seed_demo_with_case_runs_full_evaluation(monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import seed_demo

    monkeypatch.setenv("SEED_DEMO_PASSWORD", "demo-acceptance-2026")
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", "--with-case"])
    seed_demo.main()
    db = get_sessionmaker()()
    try:
        case = db.execute(select(CustomsCase).where(CustomsCase.case_no == "VIP-HQ-261008-001")).scalar_one()
        items = db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id)).scalars().all()
        assert len(items) == 3 and {i.hs_status for i in items} == {"NEEDS_REVIEW", "BLOCKED"}
        assert case.status == "BLOCKED"  # item 3 low confidence → critical
        assert any(i.code == "HS_LOW_CONFIDENCE" for i in db.execute(select(Issue).where(Issue.case_id == case.id)).scalars())
        assert {d.kind for d in db.execute(select(KnowledgeDataset)).scalars()} == {"HS_RULES", "TARIFF", "FTA", "POLICY"}
        assert all(d.is_demo for d in db.execute(select(KnowledgeDataset)).scalars())
    finally:
        db.close()


def test_seed_refuses_without_password(monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import seed_demo

    monkeypatch.delenv("SEED_DEMO_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_demo.py"])
    with pytest.raises(SystemExit):
        seed_demo.main()
