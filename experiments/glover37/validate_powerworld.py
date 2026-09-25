from __future__ import annotations

import argparse
import cmath
import csv
import math
import re
from pathlib import Path
from statistics import mean

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

RESULTS_ROOT = (
    ROOT
    / "results"
    / "glover37"
)

POWERWORLD_ROOT = (
    ROOT
    / "data"
    / "powerworld"
    / "glover37"
)

VALIDATION_ROOT = (
    RESULTS_ROOT
    / "validation"
)

STATE_ORDER = [
    "base",
    "A1",
    "A2",
    "A3",
    "B1",
    "B2",
    "B3",
]

SCENARIO_ORDER = [
    "A1",
    "A2",
    "A3",
    "B1",
    "B2",
    "B3",
]


# ============================================================
# Generic utilities
# ============================================================


def pw_float(
    value: str | None,
) -> float:
    """
    Convert PowerWorld numeric text.

    PowerWorld exports use decimal commas inside quoted CSV
    fields, e.g. "30,45826".
    """

    if value is None:
        raise ValueError(
            "Missing numeric value in PowerWorld CSV."
        )

    text = str(value).strip()

    if not text:
        raise ValueError(
            "Empty numeric value in PowerWorld CSV."
        )

    return float(
        text.replace(",", ".")
    )


def parse_bus_id(
    whoami: str,
) -> int:

    match = re.fullmatch(
        r"\s*Bus\s+'(\d+)'\s*",
        whoami or "",
    )

    if not match:
        raise ValueError(
            "Could not parse PowerWorld bus from "
            f"WhoAmI={whoami!r}"
        )

    return int(
        match.group(1)
    )


def wrapped_angle_difference_deg(
    a: float,
    b: float,
) -> float:
    """
    Signed wrapped angle difference a - b in [-180, 180).
    """

    return (
        a
        - b
        + 180.0
    ) % 360.0 - 180.0


def rmse(
    values: list[float],
) -> float:

    if not values:
        return math.nan

    return math.sqrt(
        sum(
            value * value
            for value
            in values
        )
        / len(values)
    )


def safe_percent(
    numerator: float,
    denominator: float,
) -> float:

    if abs(denominator) < 1e-15:
        return math.nan

    return (
        100.0
        * numerator
        / denominator
    )


# ============================================================
# Input paths
# ============================================================


def python_results_file(
    state: str,
) -> Path:

    return (
        RESULTS_ROOT
        / state
        / "results.csv"
    )


def powerworld_file(
    state: str,
) -> Path:

    return (
        POWERWORLD_ROOT
        / state
        / "shortcircuit.csv"
    )


# ============================================================
# Python results
# ============================================================


def read_python_results(
    state: str,
) -> dict[int, dict]:

    path = python_results_file(
        state
    )

    if not path.is_file():
        raise FileNotFoundError(
            f"Python result file not found: {path}"
        )

    data = pd.read_csv(
        path
    )

    required = {
        "bus",
        "pre_fault_V_mag",
        "pre_fault_V_ang_deg",
        "I_SCC_mag_pu",
        "I_SCC_ang_deg",
        "SCL_pu",
        "SCL_MVA",
    }

    missing = (
        required
        - set(
            data.columns
        )
    )

    if missing:
        raise ValueError(
            f"{path} is missing columns: "
            f"{sorted(missing)}"
        )

    results = {}

    for row in data.itertuples():

        bus = int(
            row.bus
        )

        if bus in results:
            raise ValueError(
                f"Duplicate Python result for bus {bus} "
                f"in {path}"
            )

        results[bus] = {
            "V_mag_pu":
                float(
                    row.pre_fault_V_mag
                ),

            "V_angle_deg":
                float(
                    row.pre_fault_V_ang_deg
                ),

            "I_mag_pu":
                float(
                    row.I_SCC_mag_pu
                ),

            "I_angle_deg":
                float(
                    row.I_SCC_ang_deg
                ),

            "SCL_pu":
                float(
                    row.SCL_pu
                ),

            "SCL_MVA":
                float(
                    row.SCL_MVA
                ),
        }

    return results


# ============================================================
# PowerWorld results
# ============================================================


def read_powerworld_results(
    state: str,
) -> dict[int, dict]:
    """
    Read one PowerWorld three-phase balanced-fault export.

    The export contains:
        line 1 : object label "Fault"
        line 2 : CSV header

    Besides fault current, FaultThevImp R/X are used to
    reconstruct the pre-fault voltage:

        V_pre = I_fault * Z_th
    """

    path = powerworld_file(
        state
    )

    if not path.is_file():
        raise FileNotFoundError(
            f"PowerWorld result file not found: {path}"
        )

    results = {}

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        object_name = (
            file.readline()
            .strip()
        )

        if not object_name:
            raise ValueError(
                f"{path} is empty."
            )

        reader = csv.DictReader(
            file
        )

        required = {
            "WhoAmI",
            "FaultType",
            "FaultImpedance",
            "FaultImpedance:1",
            "ABCPhaseI",
            "ABCPhaseAngle",
            "FaultThevImp",
            "FaultThevImp:1",
        }

        missing = (
            required
            - set(
                reader.fieldnames
                or []
            )
        )

        if missing:
            raise ValueError(
                f"{path} is missing columns: "
                f"{sorted(missing)}"
            )

        for row in reader:

            bus = parse_bus_id(
                row["WhoAmI"]
            )

            if bus in results:
                raise ValueError(
                    f"Duplicate PowerWorld result "
                    f"for bus {bus} in {path}"
                )

            fault_type = (
                row["FaultType"]
                .strip()
            )

            if fault_type != "3PB":
                raise ValueError(
                    f"{state}, bus {bus}: "
                    f"expected 3PB fault, "
                    f"found {fault_type!r}"
                )

            fault_r = pw_float(
                row[
                    "FaultImpedance"
                ]
            )

            fault_x = pw_float(
                row[
                    "FaultImpedance:1"
                ]
            )

            if (
                abs(fault_r) > 1e-12
                or abs(fault_x) > 1e-12
            ):
                raise ValueError(
                    f"{state}, bus {bus}: "
                    "expected bolted fault, "
                    f"found R={fault_r}, X={fault_x}"
                )

            i_mag = pw_float(
                row[
                    "ABCPhaseI"
                ]
            )

            i_angle_deg = (
                pw_float(
                    row[
                        "ABCPhaseAngle"
                    ]
                )
            )

            r_th = pw_float(
                row[
                    "FaultThevImp"
                ]
            )

            x_th = pw_float(
                row[
                    "FaultThevImp:1"
                ]
            )

            i_complex = (
                i_mag
                * cmath.exp(
                    1j
                    * math.radians(
                        i_angle_deg
                    )
                )
            )

            z_th = complex(
                r_th,
                x_th,
            )

            v_complex = (
                i_complex
                * z_th
            )

            v_mag = abs(
                v_complex
            )

            v_angle_deg = (
                math.degrees(
                    cmath.phase(
                        v_complex
                    )
                )
            )

            results[bus] = {
                "I_mag_pu":
                    i_mag,

                "I_angle_deg":
                    i_angle_deg,

                "R_th_pu":
                    r_th,

                "X_th_pu":
                    x_th,

                "V_mag_pu":
                    v_mag,

                "V_angle_deg":
                    v_angle_deg,

                # Conventional SCL on common pu base:
                # V_nominal_pu = 1.
                "SCL_pu":
                    i_mag,
            }

    return results


# ============================================================
# Validation level 1
#
# Absolute state:
# Python state vs PowerWorld state
# ============================================================


def compare_state(
    state: str,
) -> pd.DataFrame:

    python = read_python_results(
        state
    )

    powerworld = (
        read_powerworld_results(
            state
        )
    )

    py_buses = set(
        python
    )

    pw_buses = set(
        powerworld
    )

    if py_buses != pw_buses:

        missing_pw = sorted(
            py_buses
            - pw_buses
        )

        missing_py = sorted(
            pw_buses
            - py_buses
        )

        raise ValueError(
            f"{state}: bus sets do not match. "
            f"Missing in PW={missing_pw}; "
            f"missing in Python={missing_py}"
        )

    rows = []

    for bus in sorted(
        py_buses
    ):

        py = python[
            bus
        ]

        pw = powerworld[
            bus
        ]

        delta_i = (
            py["I_mag_pu"]
            - pw["I_mag_pu"]
        )

        delta_i_angle = (
            wrapped_angle_difference_deg(
                py["I_angle_deg"],
                pw["I_angle_deg"],
            )
        )

        delta_v = (
            py["V_mag_pu"]
            - pw["V_mag_pu"]
        )

        delta_v_angle = (
            wrapped_angle_difference_deg(
                py["V_angle_deg"],
                pw["V_angle_deg"],
            )
        )

        rows.append(
            {
                "bus":
                    bus,

                "python_I_SCC_pu":
                    py["I_mag_pu"],

                "powerworld_I_SCC_pu":
                    pw["I_mag_pu"],

                "delta_I_SCC_pu":
                    delta_i,

                "abs_delta_I_SCC_pu":
                    abs(
                        delta_i
                    ),

                "delta_I_SCC_pct_of_PW":
                    safe_percent(
                        delta_i,
                        pw["I_mag_pu"],
                    ),

                "abs_delta_I_SCC_pct_of_PW":
                    abs(
                        safe_percent(
                            delta_i,
                            pw["I_mag_pu"],
                        )
                    ),

                "python_I_angle_deg":
                    py["I_angle_deg"],

                "powerworld_I_angle_deg":
                    pw["I_angle_deg"],

                "delta_I_angle_deg":
                    delta_i_angle,

                "abs_delta_I_angle_deg":
                    abs(
                        delta_i_angle
                    ),

                "python_V_pre_pu":
                    py["V_mag_pu"],

                "powerworld_V_pre_reconstructed_pu":
                    pw["V_mag_pu"],

                "delta_V_pre_pu":
                    delta_v,

                "abs_delta_V_pre_pu":
                    abs(
                        delta_v
                    ),

                "python_V_pre_angle_deg":
                    py["V_angle_deg"],

                "powerworld_V_pre_angle_reconstructed_deg":
                    pw["V_angle_deg"],

                "delta_V_pre_angle_deg":
                    delta_v_angle,

                "abs_delta_V_pre_angle_deg":
                    abs(
                        delta_v_angle
                    ),

                "powerworld_R_th_pu":
                    pw["R_th_pu"],

                "powerworld_X_th_pu":
                    pw["X_th_pu"],
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# Validation level 2
#
# Scenario-induced change:
#
#     state - baseline
#
# Python field vs PowerWorld field
# ============================================================


def compare_change_from_base(
    scenario: str,
) -> pd.DataFrame:

    if scenario == "base":
        raise ValueError(
            "Base has no change-from-base comparison."
        )

    py_base = (
        read_python_results(
            "base"
        )
    )

    py_scenario = (
        read_python_results(
            scenario
        )
    )

    pw_base = (
        read_powerworld_results(
            "base"
        )
    )

    pw_scenario = (
        read_powerworld_results(
            scenario
        )
    )

    bus_sets = [
        set(
            py_base
        ),
        set(
            py_scenario
        ),
        set(
            pw_base
        ),
        set(
            pw_scenario
        ),
    ]

    if not all(
        buses
        == bus_sets[0]
        for buses
        in bus_sets[1:]
    ):
        raise ValueError(
            f"{scenario}: bus sets do not match "
            "for change-from-base validation."
        )

    rows = []

    for bus in sorted(
        bus_sets[0]
    ):

        py0 = (
            py_base[
                bus
            ]["SCL_pu"]
        )

        pys = (
            py_scenario[
                bus
            ]["SCL_pu"]
        )

        pw0 = (
            pw_base[
                bus
            ]["SCL_pu"]
        )

        pws = (
            pw_scenario[
                bus
            ]["SCL_pu"]
        )

        py_delta = (
            pys
            - py0
        )

        pw_delta = (
            pws
            - pw0
        )

        py_delta_pct = (
            safe_percent(
                py_delta,
                py0,
            )
        )

        pw_delta_pct = (
            safe_percent(
                pw_delta,
                pw0,
            )
        )

        error_delta = (
            py_delta
            - pw_delta
        )

        error_delta_pct = (
            py_delta_pct
            - pw_delta_pct
        )

        rows.append(
            {
                "bus":
                    bus,

                "python_base_SCL_pu":
                    py0,

                "python_scenario_SCL_pu":
                    pys,

                "python_delta_SCL_pu":
                    py_delta,

                "python_delta_SCL_pct":
                    py_delta_pct,

                "powerworld_base_SCL_pu":
                    pw0,

                "powerworld_scenario_SCL_pu":
                    pws,

                "powerworld_delta_SCL_pu":
                    pw_delta,

                "powerworld_delta_SCL_pct":
                    pw_delta_pct,

                "delta_field_error_pu":
                    error_delta,

                "abs_delta_field_error_pu":
                    abs(
                        error_delta
                    ),

                "delta_field_error_pct_points":
                    error_delta_pct,

                "abs_delta_field_error_pct_points":
                    abs(
                        error_delta_pct
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# Validation level 3
#
# A2 - A1
#
# Isolates zero-dispatch synchronized generator vs
# generator disconnection.
# ============================================================


def compare_a2_minus_a1(
) -> pd.DataFrame:

    py_a1 = (
        read_python_results(
            "A1"
        )
    )

    py_a2 = (
        read_python_results(
            "A2"
        )
    )

    pw_a1 = (
        read_powerworld_results(
            "A1"
        )
    )

    pw_a2 = (
        read_powerworld_results(
            "A2"
        )
    )

    bus_sets = [
        set(
            py_a1
        ),
        set(
            py_a2
        ),
        set(
            pw_a1
        ),
        set(
            pw_a2
        ),
    ]

    if not all(
        buses
        == bus_sets[0]
        for buses
        in bus_sets[1:]
    ):
        raise ValueError(
            "A1/A2 bus sets do not match."
        )

    rows = []

    for bus in sorted(
        bus_sets[0]
    ):

        py1 = (
            py_a1[
                bus
            ]["SCL_pu"]
        )

        py2 = (
            py_a2[
                bus
            ]["SCL_pu"]
        )

        pw1 = (
            pw_a1[
                bus
            ]["SCL_pu"]
        )

        pw2 = (
            pw_a2[
                bus
            ]["SCL_pu"]
        )

        py_delta = (
            py2
            - py1
        )

        pw_delta = (
            pw2
            - pw1
        )

        py_delta_pct = (
            safe_percent(
                py_delta,
                py1,
            )
        )

        pw_delta_pct = (
            safe_percent(
                pw_delta,
                pw1,
            )
        )

        rows.append(
            {
                "bus":
                    bus,

                "python_A1_SCL_pu":
                    py1,

                "python_A2_SCL_pu":
                    py2,

                "python_A2_minus_A1_SCL_pu":
                    py_delta,

                "python_A2_minus_A1_pct":
                    py_delta_pct,

                "powerworld_A1_SCL_pu":
                    pw1,

                "powerworld_A2_SCL_pu":
                    pw2,

                "powerworld_A2_minus_A1_SCL_pu":
                    pw_delta,

                "powerworld_A2_minus_A1_pct":
                    pw_delta_pct,

                "delta_field_error_pu":
                    (
                        py_delta
                        - pw_delta
                    ),

                "abs_delta_field_error_pu":
                    abs(
                        py_delta
                        - pw_delta
                    ),

                "delta_field_error_pct_points":
                    (
                        py_delta_pct
                        - pw_delta_pct
                    ),

                "abs_delta_field_error_pct_points":
                    abs(
                        py_delta_pct
                        - pw_delta_pct
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# Summaries
# ============================================================


def state_summary(
    state: str,
    data: pd.DataFrame,
) -> dict:

    worst_i = data.loc[
        data[
            "abs_delta_I_SCC_pct_of_PW"
        ].idxmax()
    ]

    worst_v = data.loc[
        data[
            "abs_delta_V_pre_pu"
        ].idxmax()
    ]

    return {
        "comparison":
            "state",

        "case":
            state,

        "buses":
            len(
                data
            ),

        "I_MAE_pu":
            data[
                "abs_delta_I_SCC_pu"
            ].mean(),

        "I_RMSE_pu":
            rmse(
                data[
                    "delta_I_SCC_pu"
                ].tolist()
            ),

        "I_mean_abs_error_pct":
            data[
                "abs_delta_I_SCC_pct_of_PW"
            ].mean(),

        "I_max_abs_error_pct":
            worst_i[
                "abs_delta_I_SCC_pct_of_PW"
            ],

        "I_max_abs_error_bus":
            int(
                worst_i[
                    "bus"
                ]
            ),

        "I_angle_MAE_deg":
            data[
                "abs_delta_I_angle_deg"
            ].mean(),

        "V_MAE_pu":
            data[
                "abs_delta_V_pre_pu"
            ].mean(),

        "V_max_abs_error_pu":
            worst_v[
                "abs_delta_V_pre_pu"
            ],

        "V_max_abs_error_bus":
            int(
                worst_v[
                    "bus"
                ]
            ),

        "V_angle_MAE_deg":
            data[
                "abs_delta_V_pre_angle_deg"
            ].mean(),
    }


def change_summary(
    label: str,
    data: pd.DataFrame,
) -> dict:

    worst = data.loc[
        data[
            "abs_delta_field_error_pct_points"
        ].idxmax()
    ]

    return {
        "comparison":
            "change_field",

        "case":
            label,

        "buses":
            len(
                data
            ),

        "delta_SCL_MAE_pu":
            data[
                "abs_delta_field_error_pu"
            ].mean(),

        "delta_SCL_RMSE_pu":
            rmse(
                data[
                    "delta_field_error_pu"
                ].tolist()
            ),

        "delta_SCL_MAE_pct_points":
            data[
                "abs_delta_field_error_pct_points"
            ].mean(),

        "delta_SCL_RMSE_pct_points":
            rmse(
                data[
                    "delta_field_error_pct_points"
                ].tolist()
            ),

        "delta_SCL_max_abs_error_pct_points":
            worst[
                "abs_delta_field_error_pct_points"
            ],

        "delta_SCL_max_abs_error_bus":
            int(
                worst[
                    "bus"
                ]
            ),
    }


# ============================================================
# Output
# ============================================================


def write_dataframe(
    data: pd.DataFrame,
    path: Path,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data.to_csv(
        path,
        index=False,
    )

    print(
        f"Wrote: {path}"
    )


def print_state_summary(
    summary: dict,
) -> None:

    print()
    print(
        f"{summary['case']} — "
        "Python vs PowerWorld"
    )

    print(
        "-" * 48
    )

    print(
        f"Buses: "
        f"{summary['buses']}"
    )

    print(
        "Fault-current magnitude"
    )

    print(
        f"  mean |error|     : "
        f"{summary['I_MAE_pu']:.8f} pu"
    )

    print(
        f"  RMSE             : "
        f"{summary['I_RMSE_pu']:.8f} pu"
    )

    print(
        f"  mean |error| [%] : "
        f"{summary['I_mean_abs_error_pct']:.4f} %"
    )

    print(
        f"  max  |error| [%] : "
        f"{summary['I_max_abs_error_pct']:.4f} % "
        f"(bus "
        f"{summary['I_max_abs_error_bus']})"
    )

    print(
        "Pre-fault voltage reconstructed "
        "from PowerWorld SC export"
    )

    print(
        f"  mean |error|     : "
        f"{summary['V_MAE_pu']:.8f} pu"
    )

    print(
        f"  max  |error|     : "
        f"{summary['V_max_abs_error_pu']:.8f} pu "
        f"(bus "
        f"{summary['V_max_abs_error_bus']})"
    )


def print_change_summary(
    summary: dict,
) -> None:

    print()
    print(
        f"{summary['case']} — "
        "ΔSCL field validation"
    )

    print(
        "-" * 48
    )

    print(
        f"Buses: "
        f"{summary['buses']}"
    )

    print(
        f"  mean |field error| : "
        f"{summary['delta_SCL_MAE_pct_points']:.6f} "
        "percentage points"
    )

    print(
        f"  RMSE field error   : "
        f"{summary['delta_SCL_RMSE_pct_points']:.6f} "
        "percentage points"
    )

    print(
        f"  max |field error|  : "
        f"{summary['delta_SCL_max_abs_error_pct_points']:.6f} "
        "percentage points "
        f"(bus "
        f"{summary['delta_SCL_max_abs_error_bus']})"
    )


# ============================================================
# Validation runners
# ============================================================


def validate_state(
    state: str,
) -> dict:

    data = compare_state(
        state
    )

    output = (
        VALIDATION_ROOT
        / state
        / "python_vs_powerworld.csv"
    )

    write_dataframe(
        data,
        output,
    )

    summary = (
        state_summary(
            state,
            data,
        )
    )

    print_state_summary(
        summary
    )

    return summary


def validate_change_from_base(
    scenario: str,
) -> dict:

    data = (
        compare_change_from_base(
            scenario
        )
    )

    output = (
        VALIDATION_ROOT
        / scenario
        / "delta_from_base_python_vs_powerworld.csv"
    )

    write_dataframe(
        data,
        output,
    )

    summary = (
        change_summary(
            f"{scenario} vs base",
            data,
        )
    )

    print_change_summary(
        summary
    )

    return summary


def validate_a1_a2(
) -> dict:

    data = (
        compare_a2_minus_a1()
    )

    output = (
        VALIDATION_ROOT
        / "A2_vs_A1"
        / "python_vs_powerworld.csv"
    )

    write_dataframe(
        data,
        output,
    )

    summary = (
        change_summary(
            "A2 vs A1",
            data,
        )
    )

    print_change_summary(
        summary
    )

    return summary


def validate_all(
) -> None:

    summaries = []

    # --------------------------------------------------------
    # Level 1:
    # every absolute operating state
    # --------------------------------------------------------

    for state in STATE_ORDER:

        summaries.append(
            validate_state(
                state
            )
        )

    # --------------------------------------------------------
    # Level 2:
    # scenario-induced field relative to baseline
    # --------------------------------------------------------

    for scenario in SCENARIO_ORDER:

        summaries.append(
            validate_change_from_base(
                scenario
            )
        )

    # --------------------------------------------------------
    # Level 3:
    # A2 vs A1 mechanism-isolation comparison
    # --------------------------------------------------------

    summaries.append(
        validate_a1_a2()
    )

    summary_path = (
        VALIDATION_ROOT
        / "summary.csv"
    )

    write_dataframe(
        pd.DataFrame(
            summaries
        ),
        summary_path,
    )


# ============================================================
# CLI
# ============================================================


def main(
) -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Validate Glover-37 Python short-circuit "
            "results against PowerWorld exports."
        )
    )

    group = (
        parser
        .add_mutually_exclusive_group(
            required=True
        )
    )

    group.add_argument(
        "--all",
        action="store_true",
        help=(
            "Run all state, change-field, "
            "and A1/A2 comparisons."
        ),
    )

    group.add_argument(
        "--state",
        choices=STATE_ORDER,
        help=(
            "Validate one absolute state "
            "against PowerWorld."
        ),
    )

    group.add_argument(
        "--scenario",
        choices=SCENARIO_ORDER,
        help=(
            "Validate one scenario both as an "
            "absolute state and as a change from baseline."
        ),
    )

    group.add_argument(
        "--a1-a2",
        action="store_true",
        help=(
            "Validate the direct A2-minus-A1 "
            "change field."
        ),
    )

    args = (
        parser.parse_args()
    )

    if args.all:

        validate_all()

    elif args.state:

        validate_state(
            args.state
        )

    elif args.scenario:

        summaries = [
            validate_state(
                args.scenario
            ),
            validate_change_from_base(
                args.scenario
            ),
        ]

        write_dataframe(
            pd.DataFrame(
                summaries
            ),
            (
                VALIDATION_ROOT
                / args.scenario
                / "summary.csv"
            ),
        )

    elif args.a1_a2:

        validate_a1_a2()


if __name__ == "__main__":
    main()