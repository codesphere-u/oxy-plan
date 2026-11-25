"""Tests for oxy-plan."""

from __future__ import annotations

import json

import pytest

from oxy_plan import HospitalWardProfile, plan_hospital_oxygen
from oxy_plan.cli import main as cli_main


def test_district_hospital_psa_is_cheaper_than_cylinders_and_flags_manifold_deficit() -> None:
    prof = HospitalWardProfile(
        hospital_id="FORT-PORTAL-RRH",
        nicu_cpap_beds=10,
        pediatric_beds=50,
        adult_general_beds=100,
        adult_icu_beds=8,
        maternity_beds=25,
        operating_theaters=3,
        existing_j_cylinders=12,
    )
    plan = plan_hospital_oxygen(prof)
    assert plan.baseline_flow_l_min > 200.0
    assert plan.recommended_psa_nm3_hr >= 30
    assert plan.dual_train_recommended is True
    assert plan.j_cylinder_deficit > 0
    assert plan.cost_comparison.recommended_modality == "on_site_psa"
    assert plan.cost_comparison.psa_usd_per_nm3 < plan.cost_comparison.cylinder_usd_per_nm3
    assert plan.cost_comparison.annual_savings_with_psa_usd > 50000.0


def test_tiny_health_center_prefers_cylinders_and_concentrators() -> None:
    tiny = HospitalWardProfile(
        hospital_id="HC3-RURAL",
        pediatric_beds=4,
        maternity_beds=2,
        existing_j_cylinders=10,
    )
    plan = plan_hospital_oxygen(tiny)
    assert plan.recommended_psa_nm3_hr == 5
    assert plan.cost_comparison.recommended_modality == "cylinder_supply_with_concentrators"
    assert plan.j_cylinder_deficit == 0


def test_cli_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["--nicu", "6", "--peds", "30", "--icu", "4"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["recommended_psa_nm3_hr"] >= 15
    assert out["recommended_backup_generator_kva"] >= 40
