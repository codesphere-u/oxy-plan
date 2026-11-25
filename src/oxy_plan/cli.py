"""CLI entrypoint for oxy-plan."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .planner import HospitalWardProfile, plan_hospital_oxygen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oxy-plan",
        description="Size district hospital medical oxygen demand, PSA plant, backup cylinders, and generator kVA.",
    )
    parser.add_argument("--hospital", default="DISTRICT-HOSP-1", help="Hospital ID.")
    parser.add_argument("--nicu", type=int, default=8, help="NICU/CPAP beds.")
    parser.add_argument("--peds", type=int, default=40, help="Pediatric beds.")
    parser.add_argument("--adult", type=int, default=80, help="Adult general beds.")
    parser.add_argument("--icu", type=int, default=6, help="Adult ICU beds.")
    parser.add_argument("--maternity", type=int, default=20, help="Maternity beds.")
    parser.add_argument("--theaters", type=int, default=2, help="Operating theaters.")
    parser.add_argument("--existing-cylinders", type=int, default=10, help="Existing full J-cylinders.")
    args = parser.parse_args(argv)

    plan = plan_hospital_oxygen(
        HospitalWardProfile(
            hospital_id=args.hospital,
            nicu_cpap_beds=args.nicu,
            pediatric_beds=args.peds,
            adult_general_beds=args.adult,
            adult_icu_beds=args.icu,
            maternity_beds=args.maternity,
            operating_theaters=args.theaters,
            existing_j_cylinders=args.existing_cylinders,
        )
    )
    print(json.dumps(asdict(plan), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
