#!/usr/bin/env python3
"""
Compare the repository's Newton-Raphson power-flow solution against the
PowerWorld bus-voltage solution exported in buses.csv.

Example
-------
python tools/compare_powerflow.py \
    --case cases/glover37.json \
    --powerworld data/powerworld/glover37/base/buses.csv

If --output is omitted, the comparison is written one directory above the
PowerWorld "base" directory, e.g.:

    data/powerworld/glover37/powerflow_comparison.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from statistics import mean

import numpy as np


# Running "python tools/compare_powerflow.py" makes tools/ sys.path[0].
# Add the repository root so imports from models/ work reliably.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from models.CustomNetwork import CustomNetwork
from models.PowerFlow import PowerFlow


def pw_float(value: str | None) -> float:
    """Parse PowerWorld numbers exported with either decimal comma or point."""
    if value is None:
        raise ValueError("Missing numeric value in PowerWorld CSV.")

    text = str(value).strip()
    if not text:
        raise ValueError("Empty numeric value in PowerWorld CSV.")

    return float(text.replace(",", "."))


def read_powerworld_buses(path: Path) -> dict[int, dict]:
    """
    Read a PowerWorld Bus CSV export.

    The supplied PowerWorld format has:
      line 1: object name, e.g. "Bus"
      line 2: CSV header
      remaining lines: bus data
    """
    buses: dict[int, dict] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        object_name = f.readline().strip()
        if not object_name:
            raise ValueError(f"{path} is empty.")

        reader = csv.DictReader(f)

        required = {"Number", "Vpu", "Vangle"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing)}"
            )

        for row in reader:
            bus_id = int(row["Number"].strip())

            if bus_id in buses:
                raise ValueError(
                    f"Duplicate bus {bus_id} in PowerWorld export {path}."
                )

            buses[bus_id] = {
                "name": row.get("Name", "").strip(),
                "category": row.get("BusCat", "").strip(),
                "V_pu": pw_float(row["Vpu"]),
                "angle_deg": pw_float(row["Vangle"]),
            }

    return buses


def wrapped_angle_difference_deg(a: float, b: float) -> float:
    """Return a-b wrapped to [-180, 180) degrees."""
    return (a - b + 180.0) % 360.0 - 180.0


def rmse(values: list[float]) -> float:
    if not values:
        return math.nan
    return math.sqrt(sum(v * v for v in values) / len(values))


def solve_case(case_path: Path):
    network = CustomNetwork(case_path)
    network.create_network()
    network.build_ybus()

    solver = PowerFlow()
    solution = solver.solve_power_flow(network)

    if solution is None:
        raise RuntimeError(f"Power flow did not converge for {case_path}.")

    theta_rad, voltage_pu = solution
    theta_deg = np.degrees(theta_rad)

    return network, voltage_pu, theta_deg


def compare(
    case_path: Path,
    powerworld_path: Path,
) -> list[dict]:
    network, voltage_py, theta_py = solve_case(case_path)
    pw_buses = read_powerworld_buses(powerworld_path)

    python_bus_ids = set(network.buses.keys())
    powerworld_bus_ids = set(pw_buses.keys())

    missing_in_pw = sorted(python_bus_ids - powerworld_bus_ids)
    missing_in_python = sorted(powerworld_bus_ids - python_bus_ids)

    if missing_in_pw or missing_in_python:
        messages = []
        if missing_in_pw:
            messages.append(
                f"missing from PowerWorld buses.csv: {missing_in_pw}"
            )
        if missing_in_python:
            messages.append(
                f"missing from JSON/Python network: {missing_in_python}"
            )
        raise ValueError("Bus sets do not match; " + "; ".join(messages))

    rows: list[dict] = []

    # Use the network's actual internal mapping instead of assuming bus IDs are
    # sequential or that CSV ordering equals JSON ordering.
    for idx in range(len(network.id)):
        bus_id = network.id[idx]
        pw = pw_buses[bus_id]

        py_v = float(voltage_py[idx])
        py_angle = float(theta_py[idx])

        pw_v = pw["V_pu"]
        pw_angle = pw["angle_deg"]

        delta_v = py_v - pw_v
        delta_angle = wrapped_angle_difference_deg(py_angle, pw_angle)

        rows.append({
            "bus": bus_id,
            "name": pw["name"],
            "bus_category": pw["category"],
            "powerworld_V_pu": pw_v,
            "python_V_pu": py_v,
            "delta_V_pu": delta_v,
            "abs_delta_V_pu": abs(delta_v),
            "delta_V_percent_of_PW": (
                100.0 * delta_v / pw_v if pw_v != 0.0 else math.nan
            ),
            "powerworld_angle_deg": pw_angle,
            "python_angle_deg": py_angle,
            "delta_angle_deg": delta_angle,
            "abs_delta_angle_deg": abs(delta_angle),
        })

    return rows


def print_summary(rows: list[dict]) -> None:
    dv = [row["delta_V_pu"] for row in rows]
    da = [row["delta_angle_deg"] for row in rows]

    abs_dv = [abs(x) for x in dv]
    abs_da = [abs(x) for x in da]

    worst_v = max(rows, key=lambda r: r["abs_delta_V_pu"])
    worst_a = max(rows, key=lambda r: r["abs_delta_angle_deg"])

    print()
    print("Power-flow comparison")
    print("---------------------")
    print(f"Buses compared: {len(rows)}")
    print()
    print("Voltage magnitude")
    print(f"  mean |dV| : {mean(abs_dv):.8f} pu")
    print(f"  RMSE dV   : {rmse(dv):.8f} pu")
    print(
        f"  max  |dV| : {worst_v['abs_delta_V_pu']:.8f} pu "
        f"(bus {worst_v['bus']})"
    )
    print()
    print("Voltage angle")
    print(f"  mean |dtheta| : {mean(abs_da):.6f} deg")
    print(f"  RMSE dtheta   : {rmse(da):.6f} deg")
    print(
        f"  max  |dtheta| : {worst_a['abs_delta_angle_deg']:.6f} deg "
        f"(bus {worst_a['bus']})"
    )


def write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "bus",
        "name",
        "bus_category",
        "powerworld_V_pu",
        "python_V_pu",
        "delta_V_pu",
        "abs_delta_V_pu",
        "delta_V_percent_of_PW",
        "powerworld_angle_deg",
        "python_angle_deg",
        "delta_angle_deg",
        "abs_delta_angle_deg",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def default_output_path(powerworld_path: Path) -> Path:
    """
    For:
      data/powerworld/glover37/base/buses.csv

    return:
      data/powerworld/glover37/powerflow_comparison.csv
    """
    if powerworld_path.parent.name == "base":
        return powerworld_path.parent.parent / "powerflow_comparison.csv"

    return powerworld_path.with_name("powerflow_comparison.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Python power-flow bus voltages against a PowerWorld "
            "buses.csv export."
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
        help=(
            "PowerWorld buses.csv containing the solved Vpu and Vangle values."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Comparison CSV. Defaults to powerflow_comparison.csv alongside "
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
            f"PowerWorld bus export not found: {powerworld_path}"
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
