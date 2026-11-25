"""WHO ward medical oxygen demand, PSA plant sizing, J-cylinder autonomy & cost/Nm3 comparator."""

from __future__ import annotations

import math
from dataclasses import dataclass

# WHO ward defaults: (flow_l_min_per_active_bed, fraction_of_beds_on_oxygen)
WARD_OXYGEN_DEFAULTS: dict[str, tuple[float, float]] = {
    "nicu_cpap": (4.0, 0.65),
    "pediatric_ward": (2.0, 0.35),
    "adult_general": (4.0, 0.15),
    "adult_icu": (15.0, 0.80),
    "maternity_labor": (5.0, 0.20),
    "operating_theater": (7.0, 0.50),
}

_STANDARD_PSA_NM3_HR: tuple[int, ...] = (5, 10, 15, 20, 30, 40, 50, 60, 80, 100)
_J_CYLINDER_USABLE_NM3 = 6.1  # Standard 47L / 150-bar J-cylinder (~6.8 m3 nominal, 10% heel)
_L_MIN_PER_NM3_HR = 1000.0 / 60.0


@dataclass(frozen=True)
class HospitalWardProfile:
    """Bed counts by clinical department for a district or referral hospital."""

    hospital_id: str
    nicu_cpap_beds: int = 0
    pediatric_beds: int = 0
    adult_general_beds: int = 0
    adult_icu_beds: int = 0
    maternity_beds: int = 0
    operating_theaters: int = 0
    surge_multiplier: float = 1.75  # Seasonal pneumonia/malaria surge margin
    backup_autonomy_days: float = 3.0  # WHO minimum 3-day cylinder manifold reserve
    existing_j_cylinders: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.nicu_cpap_beds,
            self.pediatric_beds,
            self.adult_general_beds,
            self.adult_icu_beds,
            self.maternity_beds,
            self.operating_theaters,
        )
        if any(c < 0 for c in counts) or sum(counts) == 0:
            raise ValueError("Hospital must have non-negative bed counts and at least one clinical bed/theater")
        if self.surge_multiplier < 1.0 or self.backup_autonomy_days <= 0.0:
            raise ValueError("Invalid surge_multiplier or backup_autonomy_days")


@dataclass(frozen=True)
class OxygenCostComparison:
    """10-year levelized cost per Nm3 comparing on-site PSA vs. refilled J-cylinders."""

    annual_oxygen_nm3: float
    psa_capex_usd: float
    psa_usd_per_nm3: float
    cylinder_usd_per_nm3: float
    recommended_modality: str  # "on_site_psa" or "cylinder_supply_with_concentrators"
    annual_savings_with_psa_usd: float


@dataclass(frozen=True)
class HospitalOxygenPlan:
    """Complete WHO oxygen demand, PSA plant, backup manifold, and generator sizing."""

    hospital_id: str
    ward_baseline_l_min: dict[str, float]
    baseline_flow_l_min: float
    peak_surge_flow_l_min: float
    baseline_nm3_day: float
    peak_surge_nm3_hr: float
    recommended_psa_nm3_hr: int
    dual_train_recommended: bool
    psa_running_power_kw: float
    recommended_backup_generator_kva: int
    j_cylinders_per_day_baseline: float
    backup_manifold_j_cylinders_required: int
    j_cylinder_deficit: int
    cost_comparison: OxygenCostComparison
    warnings: tuple[str, ...]


def _pick_psa_size(required_nm3_hr: float) -> int:
    for sz in _STANDARD_PSA_NM3_HR:
        if sz >= required_nm3_hr:
            return sz
    return int(math.ceil(required_nm3_hr / 20.0) * 20)


def plan_hospital_oxygen(
    profile: HospitalWardProfile,
    *,
    electricity_usd_kwh: float = 0.18,
    cylinder_refill_delivered_usd: float = 28.0,
    psa_capex_usd_per_nm3_hr: float = 8500.0,
    psa_life_years: int = 10,
) -> HospitalOxygenPlan:
    """Size medical O2 demand, PSA capacity, backup J-cylinder manifold, generator kVA & cost/Nm3."""
    bed_map = {
        "nicu_cpap": profile.nicu_cpap_beds,
        "pediatric_ward": profile.pediatric_beds,
        "adult_general": profile.adult_general_beds,
        "adult_icu": profile.adult_icu_beds,
        "maternity_labor": profile.maternity_beds,
        "operating_theater": profile.operating_theaters,
    }
    ward_lpm: dict[str, float] = {}
    for ward, beds in bed_map.items():
        flow_bed, occ = WARD_OXYGEN_DEFAULTS[ward]
        ward_lpm[ward] = round(beds * flow_bed * occ, 2)

    base_lpm = sum(ward_lpm.values())
    peak_lpm = base_lpm * profile.surge_multiplier
    base_nm3_hr = base_lpm / _L_MIN_PER_NM3_HR
    base_nm3_day = base_nm3_hr * 24.0
    peak_nm3_hr = peak_lpm / _L_MIN_PER_NM3_HR

    # Size PSA so it meets peak surge within a 20h/day duty cycle (4h maintenance/regeneration window)
    psa_req_nm3_hr = peak_nm3_hr * (24.0 / 20.0)
    psa_size = _pick_psa_size(psa_req_nm3_hr)
    dual_train = psa_size >= 30 or profile.adult_icu_beds >= 6

    # Typical PSA compressor + dryer + cylinder booster power: ~1.45 kW per Nm3/hr capacity
    running_kw = psa_size * 1.45
    # Generator sized with 2.2x starting-inrush & 0.8 power-factor headroom
    gen_kva = max(15, int(math.ceil((running_kw * 2.2 / 0.8) / 5.0) * 5))

    cyl_per_day = base_nm3_day / _J_CYLINDER_USABLE_NM3
    backup_cyls = max(4, math.ceil(cyl_per_day * profile.backup_autonomy_days))
    cyl_deficit = max(0, backup_cyls - profile.existing_j_cylinders)

    # 10-year TCO comparator (turnkey PSA includes compressor, dryer, housing, analyzer & piping floor)
    annual_nm3 = base_nm3_day * 365.0
    psa_capex = max(95000.0, psa_size * psa_capex_usd_per_nm3_hr)
    # Annualized CAPEX + electricity (1.25 kWh/Nm3) + biomedical preventive maintenance / sieve budget
    annual_maint = max(5500.0, psa_capex * 0.06)
    annual_psa_cost = (psa_capex / psa_life_years) + (annual_nm3 * 1.25 * electricity_usd_kwh) + annual_maint
    psa_unit_cost = annual_psa_cost / max(1.0, annual_nm3)

    cyl_unit_cost = cylinder_refill_delivered_usd / _J_CYLINDER_USABLE_NM3
    annual_cyl_cost = annual_nm3 * cyl_unit_cost
    annual_savings = annual_cyl_cost - annual_psa_cost
    modality = "on_site_psa" if psa_unit_cost < cyl_unit_cost else "cylinder_supply_with_concentrators"

    warnings: list[str] = []
    if cyl_deficit > 0:
        warnings.append(
            f"BACKUP MANIFOLD DEFICIT: hospital holds {profile.existing_j_cylinders} J-cylinders vs "
            f"{backup_cyls} required for {profile.backup_autonomy_days:g}-day outage autonomy."
        )
    if dual_train:
        warnings.append(
            f"DUAL-TRAIN REDUNDANCY RECOMMENDED: split {psa_size} Nm3/hr across 2x {psa_size // 2} Nm3/hr skids "
            "to protect ICU/NICU continuity during compressor servicing."
        )

    return HospitalOxygenPlan(
        hospital_id=profile.hospital_id,
        ward_baseline_l_min=ward_lpm,
        baseline_flow_l_min=round(base_lpm, 2),
        peak_surge_flow_l_min=round(peak_lpm, 2),
        baseline_nm3_day=round(base_nm3_day, 2),
        peak_surge_nm3_hr=round(peak_nm3_hr, 2),
        recommended_psa_nm3_hr=psa_size,
        dual_train_recommended=dual_train,
        psa_running_power_kw=round(running_kw, 2),
        recommended_backup_generator_kva=gen_kva,
        j_cylinders_per_day_baseline=round(cyl_per_day, 2),
        backup_manifold_j_cylinders_required=backup_cyls,
        j_cylinder_deficit=cyl_deficit,
        cost_comparison=OxygenCostComparison(
            annual_oxygen_nm3=round(annual_nm3, 1),
            psa_capex_usd=round(psa_capex, 2),
            psa_usd_per_nm3=round(psa_unit_cost, 3),
            cylinder_usd_per_nm3=round(cyl_unit_cost, 3),
            recommended_modality=modality,
            annual_savings_with_psa_usd=round(annual_savings, 2),
        ),
        warnings=tuple(warnings),
    )
