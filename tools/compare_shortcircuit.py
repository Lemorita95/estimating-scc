#!/usr/bin/env python3
"""
Compare SCC results from the repository implementation against a PowerWorld
three-phase balanced fault export.

Expected PowerWorld fields:
  - WhoAmI          e.g. "Bus '1'"
  - FaultType       expected "3PB"
  - FaultImpedance  expected 0
  - ABCPhaseI       fault-current magnitude [pu]
  - ABCPhaseAngle   fault-current angle [deg]

Example
-------
python tools/compare_shortcircuit.py \
    --case cases/glover37.json \
    --powerworld data/powerworld/glover37/base/short_circuit.csv

Default output:
    data/powerworld/glover37/shortcircuit_comparison.csv
"""

from __future__ import annotations

import argparse
import csv
import cmath
import math
import re
import sys
from pathlib import Path
from statistics import mean

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from models.CustomNetwork import CustomNetwork
from models.PowerFlow import PowerFlow
from models.ShortCircuit import ShortCircuit as SC


def pw_float(value: str | None) -> float:
    if value is None:
        raise ValueError("Missing numeric value in PowerWorld CSV.")
    text = str(value).strip()
    if not text:
        raise ValueError("Empty numeric value in PowerWorld CSV.")
    return float(text.replace(",", "."))


def parse_bus_id(whoami: str) -> int:
    match = re.fullmatch(r"\s*Bus\s+'(\d+)'\s*", whoami or "")
    if not match:
        raise ValueError(f"Could not parse PowerWorld bus from WhoAmI={whoami!r}")
    return int(match.group(1))


def read_powerworld_faults(path: Path) -> dict[int, dict]:
    """
    Read a PowerWorld Fault CSV export.

    The supplied format has:
      line 1: object label "Fault"
      line 2: CSV header
      remaining lines: fault results
    """
    faults: dict[int, dict] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        object_name = f.readline().strip()
        if not object_name:
            raise ValueError(f"{path} is empty.")

        reader = csv.DictReader(f)
        required = {
            "WhoAmI",
            "FaultType",
            "FaultImpedance",
            "ABCPhaseI",
            "ABCPhaseAngle",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing)}"
            )

        for row in reader:
            bus_id = parse_bus_id(row["WhoAmI"])

            if bus_id in faults:
                raise ValueError(f"Duplicate fault result for bus {bus_id}.")

            fault_type = row["FaultType"].strip()
            if fault_type != "3PB":
                raise ValueError(
                    f"Bus {bus_id}: expected 3PB fault, found {fault_type!r}."
                )

            rf = pw_float(row["FaultImpedance"])
            # In the supplied PowerWorld export the second FaultImpedance
            # column appears as FaultImpedance:1.
            xf = pw_float(row.get("FaultImpedance:1", "0"))
            if abs(rf) > 1e-12 or abs(xf) > 1e-12:
                raise ValueError(
                    f"Bus {bus_id}: expected bolted fault, found "
                    f"R={rf}, X={xf}."
                )

            faults[bus_id] = {
                "I_mag_pu": pw_float(row["ABCPhaseI"]),
                "I_angle_deg": pw_float(row["ABCPhaseAngle"]),
            }

    return faults


def wrapped_angle_difference_deg(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def rmse(values: list[float]) -> float:
    if not values:
        return math.nan
    return math.sqrt(sum(v * v for v in values) / len(values))


def solve_short_circuit(case_path: Path) -> tuple[CustomNetwork, dict[int, complex]]:
    """
    Reproduce the current iterative SCC workflow used by run_cases.py,
    without writing the standard report files.
    """
    network = CustomNetwork(case_path)
    network.create_network()

    network.build_ybus()
    passive_ybus = network.YBus

    pf_solver = PowerFlow()

    pf_solution = pf_solver.solve_power_flow(network)
    if pf_solution is None:
        raise RuntimeError(f"Power flow did not converge for {case_path}.")

    theta, voltage = pf_solution

    v_complex = np.array(
        [v * np.exp(1j * t) for t, v in zip(theta, voltage)],
        dtype=complex,
    )

    # Same pre-fault active-element state construction as iterative()
    # in run_cases.py.
    active_element_flow = pf_solver.get_active_elements_flow(
        network, np.concatenate((theta, voltage))
    )
    active_element_status = pf_solver.get_active_element_status(network)

    active_elements = network.get_active_elements(
        v_complex,
        active_element_flow,
        active_element_status,
    )

    currents: dict[int, complex] = {}

    print("\t\tSolving Short-circuit using Newton-Raphson method...")
    for bus_id in network.buses.keys():
        current = SC.SCC_NR(
            network.idx[bus_id],
            v_complex,
            passive_ybus,
            active_elements,
        )
        currents[bus_id] = current

    return network, currents


def compare(case_path: Path, powerworld_path: Path) -> list[dict]:
    network, python_currents = solve_short_circuit(case_path)
    pw_faults = read_powerworld_faults(powerworld_path)

    python_bus_ids = set(network.buses.keys())
    pw_bus_ids = set(pw_faults.keys())

    missing_in_pw = sorted(python_bus_ids - pw_bus_ids)
    missing_in_python = sorted(pw_bus_ids - python_bus_ids)

    if missing_in_pw or missing_in_python:
        messages = []
        if missing_in_pw:
            messages.append(f"missing from PowerWorld: {missing_in_pw}")
        if missing_in_python:
            messages.append(f"missing from Python case: {missing_in_python}")
        raise ValueError("Fault bus sets do not match; " + "; ".join(messages))

    rows: list[dict] = []

    for bus_id in network.buses.keys():
        i_py = python_currents[bus_id]

        py_mag = abs(i_py)
        py_angle = math.degrees(cmath.phase(i_py))

        pw_mag = pw_faults[bus_id]["I_mag_pu"]
        pw_angle = pw_faults[bus_id]["I_angle_deg"]

        delta_mag = py_mag - pw_mag
        delta_angle = wrapped_angle_difference_deg(py_angle, pw_angle)

        rows.append({
            "bus": bus_id,
            "powerworld_I_mag_pu": pw_mag,
            "python_I_mag_pu": py_mag,
            "delta_I_pu": delta_mag,
            "abs_delta_I_pu": abs(delta_mag),
            "delta_I_percent_of_PW": (
                100.0 * delta_mag / pw_mag if pw_mag != 0.0 else math.nan
            ),
            "abs_delta_I_percent_of_PW": (
                100.0 * abs(delta_mag) / pw_mag if pw_mag != 0.0 else math.nan
            ),
            "powerworld_I_angle_deg": pw_angle,
            "python_I_angle_deg": py_angle,
            "delta_I_angle_deg": delta_angle,
            "abs_delta_I_angle_deg": abs(delta_angle),
        })

    return rows


def print_summary(rows: list[dict]) -> None:
    d_i = [r["delta_I_pu"] for r in rows]
    abs_d_i = [r["abs_delta_I_pu"] for r in rows]
    abs_pct = [r["abs_delta_I_percent_of_PW"] for r in rows]
    d_angle = [r["delta_I_angle_deg"] for r in rows]
    abs_d_angle = [r["abs_delta_I_angle_deg"] for r in rows]

    worst_i = max(rows, key=lambda r: r["abs_delta_I_pu"])
    worst_pct = max(rows, key=lambda r: r["abs_delta_I_percent_of_PW"])
    worst_angle = max(rows, key=lambda r: r["abs_delta_I_angle_deg"])

    print()
    print("Short-circuit comparison")
    print("------------------------")
    print(f"Buses compared: {len(rows)}")
    print()
    print("Fault-current magnitude")
    print(f"  mean |dI|     : {mean(abs_d_i):.8f} pu")
    print(f"  RMSE dI       : {rmse(d_i):.8f} pu")
    print(
        f"  max  |dI|     : {worst_i['abs_delta_I_pu']:.8f} pu "
        f"(bus {worst_i['bus']})"
    )
    print(f"  mean |dI| [%] : {mean(abs_pct):.4f} %")
    print(
        f"  max  |dI| [%] : {worst_pct['abs_delta_I_percent_of_PW']:.4f} % "
        f"(bus {worst_pct['bus']})"
    )
    print()
    print("Fault-current angle")
    print(f"  mean |dtheta| : {mean(abs_d_angle):.6f} deg")
    print(f"  RMSE dtheta   : {rmse(d_angle):.6f} deg")
    print(
        f"  max  |dtheta| : {worst_angle['abs_delta_I_angle_deg']:.6f} deg "
        f"(bus {worst_angle['bus']})"
    )


def write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "bus",
        "powerworld_I_mag_pu",
        "python_I_mag_pu",
        "delta_I_pu",
        "abs_delta_I_pu",
        "delta_I_percent_of_PW",
        "abs_delta_I_percent_of_PW",
        "powerworld_I_angle_deg",
        "python_I_angle_deg",
        "delta_I_angle_deg",
        "abs_delta_I_angle_deg",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def default_output_path(powerworld_path: Path) -> Path:
    if powerworld_path.parent.name == "base":
        return powerworld_path.parent.parent / "shortcircuit_comparison.csv"
    return powerworld_path.with_name("shortcircuit_comparison.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare iterative Python SCC results against a PowerWorld "
            "three-phase balanced fault export."
        )
    )
    parser.add_argument(
        "--case",
        required=True,
        type=Path,
        help="Solver-ready JSON case, e.g. cases/glover37.json.",
    )
    parser.add_argument(
        "--powerworld",
        required=True,
        type=Path,
        help="PowerWorld short_circuit.csv export.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Comparison CSV. Defaults to shortcircuit_comparison.csv alongside "
            "the PowerWorld case's base/ directory."
        ),
    )
    args = parser.parse_args()

    case_path = args.case.resolve()
    powerworld_path = args.powerworld.resolve()

    if not case_path.is_file():
        raise FileNotFoundError(f"JSON case not found: {case_path}")
    if not powerworld_path.is_file():
        raise FileNotFoundError(
            f"PowerWorld SCC export not found: {powerworld_path}"
        )

    output_path = (
        args.output.resolve()
        if args.output is not None
        else default_output_path(powerworld_path)
    )

    rows = compare(case_path, powerworld_path)
    write_csv(rows, output_path)
    print_summary(rows)

    print()
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
