import os
import csv
import numpy as np
import matplotlib.pyplot as plt
import json
import matplotlib.colors as mcolors
import textwrap
import pandas as pd

from plot_config import set_plot_style, SINGLE_COL, COLORS, HATCHES

set_plot_style()

reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
meta_dir = os.path.join(reports_dir, 'meta_files')
images_dir = os.path.join(os.path.dirname(__file__), 'images')
tables_dir = os.path.join(os.path.dirname(__file__), 'tables')

def visualize_timeseries(file, file_out, buses=None):
    if isinstance(buses, str):
        buses = [buses]
    collected = {}
    with open(os.path.join(reports_dir, file), newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            bus = row['bus']
            if buses is not None and bus not in buses:
                continue
            if bus not in collected:
                collected[bus] = ([], [])
            collected[bus][0].append(int(row['step']))
            collected[bus][1].append(float(row['I_SCC_mag']))

    fig, ax = plt.subplots(figsize=(SINGLE_COL, 2.5))
    for bus, (steps, data) in collected.items():
        plt.plot(np.array(steps), np.array(data), label=bus, markersize=3, linewidth=1.2)

    ax.spines["left"].set_position(("outward", 4))
    ax.spines["bottom"].set_position(("outward", 4))

    # plt.axvline(9, color='black', alpha=0.5, ls='dotted')
    # plt.axvline(10, color='black', alpha=0.5, ls='dotted')
    # plt.axvline(12, color='black', alpha=0.5, ls='dotted')
    ax.set_ylabel("Current [p.u.]")
    ax.set_xlabel("Hour of day")
    ax.legend(loc='upper left')
    
    plt.savefig(os.path.join(images_dir, file_out), bbox_inches="tight")
    plt.show()

def visualize_datasets(*files, file_out, labels, colors=None, hatches=None, do_show=False):
    _colors  = colors  if colors  is not None else COLORS
    _hatches = hatches if hatches is not None else HATCHES
    
    buses = None
    datasets = []

    for file in files:
        values = []
        file_buses = []
        with open(os.path.join(reports_dir, file), newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                file_buses.append(row['bus'])
                values.append(float(row['I_SCC_mag']))
        if buses is None:
            buses = np.array(file_buses)
        datasets.append(np.array(values))

    x = np.arange(len(buses))
    n = len(files)
    width = 0.8 / n

    fig, ax = plt.subplots(figsize=(SINGLE_COL, 2.5))
    for i, (file, data) in enumerate(zip(files, datasets)):
        offset = (i - n / 2 + 0.5) * width
        ax.bar(x + offset, data, width,
               color=_colors[i % len(_colors)],
               edgecolor="black",
               linewidth=0.5,
               hatch=_hatches[i % len(_hatches)],
               label=labels[i])

    ax.spines["left"].set_position(("outward", 4))
    ax.spines["bottom"].set_position(("outward", 4))
    ax.set_xlabel("Bus")
    ax.set_ylabel(r"$|I_{{k3}}^{{''}}|$")
    ax.set_xticks(x)
    ax.set_xticklabels(buses)
    ax.legend(fontsize=8)
    
    plt.tight_layout()
    plt.savefig(os.path.join(images_dir, file_out), bbox_inches="tight")
    if do_show:
        plt.show()
    plt.close(fig)

def compare_datasets(file1, file2, labels, include_summary=True, do_print=False):
    # --- Helper functions ---
    def load_csv(file):
        buses, values = [], []
        with open(os.path.join(reports_dir, file), newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                buses.append(row['bus'])
                values.append(float(row['I_SCC_mag']))
        return buses, np.array(values)

    def load_meta(file):
        meta_file = file.removesuffix(".csv") + "_meta.json"
        with open(os.path.join(meta_dir, meta_file)) as f:
            return json.load(f)

    def fmt_signed(x, decimals=2):
        if pd.isna(x):
            return ""
        return f"{x:+.{decimals}f}"

    # --- Load data ---
    buses, v1 = load_csv(file1)
    _, v2     = load_csv(file2)

    # --- Table 1: per-bus comparison ---
    delta_pct = np.where(v1 != 0, (v2 - v1) / v1 * 100, np.nan)
    df1 = pd.DataFrame({
        "Bus": buses,
        labels[0] + r" (p.u.)": v1,
        labels[1] + r" (p.u.)": v2,
        r"$\Delta$ (\%)": delta_pct
    })
    df1[r"$\Delta$ (\%)"] = df1[r"$\Delta$ (\%)"].map(lambda x: fmt_signed(x, 2))

    latex1 = df1.to_latex(
        index=False,
        escape=False,
        column_format="lrrr",
        float_format="%.2f"
    )

    # --- Table 2: system summary (optional) ---
    if not include_summary:
        return latex1, None

    m1 = load_meta(file1)
    m2 = load_meta(file2)

    def summary(m):
        total_gen  = (m["total_gen_MW"] + m["total_conv_MW"])
        total_load = (m["total_load_MW"] + m["total_shunt_MW"])
        ren_pct    = (m["total_conv_MW"] / total_gen * 100) if total_gen != 0 else 0
        losses_pct = (m["total_losses_MW"] / total_gen * 100) if total_gen != 0 else 0
        return {
            "Total generation (MW)": total_gen,
            "Total renewable (MW)":  m["total_conv_MW"],
            r"Renewable share (\%)": ren_pct,
            "Total load (MW)":       total_load,
            r"Losses (\%)":          losses_pct,
        }

    s1, s2 = summary(m1), summary(m2)
    delta2 = {
        k: (s2[k] - s1[k]) / s1[k] * 100 if s1[k] != 0 else np.nan
        for k in s1
    }

    df2 = pd.DataFrame({
        "Metric": list(s1.keys()),
        labels[0]: list(s1.values()),
        labels[1]: list(s2.values()),
        r"$\Delta$ (\%)": list(delta2.values())
    })
    df2[r"$\Delta$ (\%)"] = df2[r"$\Delta$ (\%)"].map(lambda x: fmt_signed(x, 2))

    latex2 = df2.to_latex(
        index=False,
        escape=False,
        column_format="lrrr",
        float_format="%.2f"
    )

    if do_print:
        print("\nPer-bus comparison:")
        print(df1.to_string(index=False, float_format="%.2f"))

        print("\nSystem summary:")
        print(df2.to_string(index=False, float_format="%.2f"))

    return latex1, latex2

def plot_error_heatmap(cases: dict[str, tuple[str, str]], file_out):
    """
    cases = {
        "case_1": ("baseline.csv", "high_load.csv"),
        "case_2": ("baseline.csv", "gen_trip.csv"),
        ...
    }
    """
    def load_csv(file):
        buses, values = [], []
        with open(os.path.join(reports_dir, file), newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                buses.append(row['bus'])
                values.append(float(row['I_SCC_mag']))
        return buses, np.array(values)

    case_names = [textwrap.fill(name, width=20) for name in cases.keys()]
    buses = None
    error_matrix = []

    for file1, file2 in cases.values():
        b, v1 = load_csv(file1)
        _, v2  = load_csv(file2)
        if buses is None:
            buses = b
        pct_err = (v2 - v1) / v1 * 100
        error_matrix.append(pct_err)

    error_matrix = np.array(error_matrix)  # shape: (n_cases, n_buses)

    limit = np.abs(error_matrix).max()
    norm  = mcolors.TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)

    fig, ax = plt.subplots(figsize=(max(8, len(buses) * 0.6), max(4, len(case_names) * 0.5)))
    im = ax.imshow(error_matrix, aspect="auto", cmap="RdBu", norm=norm)

    # minor ticks for gridlines between cells
    ax.set_xticks(np.arange(-0.5, len(buses), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(case_names), 1), minor=True)
    ax.grid(False)
    ax.grid(which="minor", color="grey", linewidth=1.0, alpha=0.25)
    ax.tick_params(which="minor", length=0)

    # major ticks for labels
    ax.set_xticks(range(len(buses)))
    ax.set_xticklabels(buses, rotation=0, ha="right", fontsize=10)
    ax.set_yticks(range(len(case_names)))
    ax.set_yticklabels(case_names, fontsize=10)

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Change (%)", fontsize=12)
    cbar.ax.tick_params(labelsize=10)
    ax.set_xlabel("Bus", fontsize=10)
    # ax.set_ylabel("Case")
    ax.set_title(r"$\left(\dfrac{I_{SC,Simulated}-I_{SC,Reference}}{I_{SC,Reference}}\right)100\%$", fontsize=14)

    plt.tight_layout()
    plt.savefig(os.path.join(images_dir, file_out), format="pdf", bbox_inches="tight")
    plt.show()

def compare_datasets_S(file1, file2, labels, bus_filter=None, do_print=False):
    # --- Helper functions ---
    def load_csv(file):
        buses, p_gen, q_gen, p_conv, q_conv = [], [], [], [], []
        with open(os.path.join(reports_dir, file), newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                buses.append(int(row['bus']))
                p_gen.append(float(row['P_gen']))
                q_gen.append(float(row['Q_gen']))
                p_conv.append(float(row['P_conv']))
                q_conv.append(float(row['Q_conv']))
        return buses, np.array(p_gen), np.array(q_gen), np.array(p_conv), np.array(q_conv)

    def fmt_signed(x, decimals=2):
        if pd.isna(x):
            return ""
        return f"{x:+.{decimals}f}"

    # --- Load data ---
    buses, p_gen1, q_gen1, p_conv1, q_conv1 = load_csv(file1)
    _,     p_gen2, q_gen2, p_conv2, q_conv2 = load_csv(file2)
    s_gen1  = np.sqrt(p_gen1**2  + q_gen1**2)
    s_gen2  = np.sqrt(p_gen2**2  + q_gen2**2)

    # --- Deltas ---
    # delta_P  = np.where(p_gen1  > 1e-6, (p_gen2  - p_gen1)  / p_gen1  * 100, 0)
    # delta_Q  = np.where(q_gen1  != 0, (q_gen2  - q_gen1)  / q_gen1  * 100, 0)
    delta_S  = np.where(s_gen1  > 1e-6, (s_gen2  - s_gen1)  / s_gen1  * 100, 0)

    # --- Build DataFrame ---
    df = pd.DataFrame({
        "Bus": buses,
        f"{labels[0]} S (MVA)": s_gen1*100,
        f"{labels[1]} S (MVA)": s_gen2*100,
        r"$\Delta_{S}$ (\%)": delta_S,
        # f"{labels[0]} Q (MVAr)": q_gen1*100,
        # f"{labels[1]} Q (MVAr)": q_gen2*100,
        # r"$\Delta_{Q}$ (\%)": delta_Q,
    })

    # --- Apply bus filter ---
    if bus_filter is not None:
        df = df[df["Bus"].isin(bus_filter)].reset_index(drop=True)

    # --- Format delta columns ---
    df[r"$\Delta_{S}$ (\%)"]  = df[r"$\Delta_{S}$ (\%)"].map(lambda x: fmt_signed(x, 2))
    # df[r"$\Delta_{Q}$ (\%)"]  = df[r"$\Delta_{Q}$ (\%)"].map(lambda x: fmt_signed(x, 2))

    # --- LaTeX ---
    latex = df.to_latex(
        index=False,
        escape=False,
        column_format="lrrrrrr",
        float_format="%.2f"
    )

    if do_print:
        print("\nPer-bus generation comparison:")
        print(df.to_string(index=False, float_format="%.2f"))

    return latex

def plot_delta_boxplot(ref_file, files, labels, file_out, do_show=False):
    """
    ref_file : str         – the reference CSV
    files    : list[str]   – one or more comparison CSVs
    labels   : list[str]   – x-axis label for each file in `files`
    """
    assert len(files) == len(labels), "files and labels must be the same length"

    def load_csv(file):
        buses, values = [], []
        with open(os.path.join(reports_dir, file), newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                buses.append(row['bus'])
                values.append(float(row['I_SCC_mag']))
        return buses, np.array(values)

    _, v_ref = load_csv(ref_file)

    deltas = []
    for file in files:
        _, v = load_csv(file)
        delta = v-v_ref#np.where(v_ref != 0, (v - v_ref) / v_ref * 100, np.nan)
        deltas.append(delta)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.boxplot(deltas, tick_labels=labels)

    ax.axhline(0, color='gray', linestyle='--', linewidth=0.8)
    ax.set_ylabel(r"$\Delta I_{SC}$ (p.u.)")
    ax.set_xlabel(r"Pre-defined Voltage $V\angle0.0^\circ$ p.u.")
    # ax.set_title(r"Buses $I_{SCC}$ deviation from reference for a given pre-defined voltage magnitude")
    ax.spines["left"].set_position(("outward", 4))
    ax.spines["bottom"].set_position(("outward", 4))
    plt.tight_layout()
    plt.savefig(os.path.join(images_dir, file_out), bbox_inches="tight")
    if do_show:
        plt.show()
    plt.close(fig)

default_labels = ['Reference', 'Simulated']
buses = [1, 2, 3, 6, 8, 12, 13, 14]
default_export = [True, True, True, False] # summary, bar chart, bus-wise, generators loading
analysis_tasks = {
    '2-1': [('CASE_0.csv', '2-1.csv'), default_labels, 'Low load', default_export],
    '2-2': [('CASE_0.csv', '2-2.csv'), default_labels, 'High load', default_export],
    '2-3': [('CASE_0.csv', '2-3.csv'), default_labels, 'Load 3 disconnection', [True, False, True, False]],
    '2-4': [('CASE_0.csv', '2-4.csv'), default_labels, 'Line 4-5 disconnection', default_export],
    '3-1': [('3-0.csv', '3-1.csv'), default_labels, 'Converter penetration', [True, False, True, True]],
    '3-2': [('3-0.csv', '3-2.csv'), default_labels, 'Synchronous generator phase-out', default_export],
    '3-3': [('3-0.csv', '3-3.csv'), default_labels, 'No synchronous generator', [True, True, True, True]],
    '4-1': [('4-0.csv', '4-1.csv'), default_labels, 'Neglect loads', [False, False, True, False]],
    '4-2': [('4-2A.csv', '4-2B.csv'), default_labels, 'Neglect converters', [False, False, True, False]],
    '4-3': [('4-3A.csv', '4-3B.csv'), default_labels, 'Neglect external grid', [False, True, True, False]],
    '4-4_095': [('4-0.csv', '4-4_095.csv'), default_labels, 'Complex voltage assumption: 0.95', [False, False, False, False]],
    '4-4_100': [('4-0.csv', '4-4_100.csv'), default_labels, 'Complex voltage assumption: 1.00', [False, False, False, False]],
    '4-4': [('4-0.csv', '4-4.csv'), default_labels, 'Complex voltage assumption: 1.05', [False, False, True, False]],
    '4-4_110': [('4-0.csv', '4-4_110.csv'), default_labels, 'Complex voltage assumption: 1.10', [False, False, False, False]],
    '4-5': [('4-0.csv', '4-5.csv'), default_labels, 'Minimal parametrization: proposed method', [False, False, True, False]],
    'classic_4-5': [('4-0.csv', 'classic_4-5.csv'), ['Reference', 'Traditional'], 'Minimal parametrization: traditional method', [False, False, True, False]],
    'CI_4-5': [('4-5.csv', 'classic_4-5.csv'), ['Simulated', 'Traditional'], 'Minimal parametrization: Proposed vs Traditional', [False, False, True, False]],
}

# for k, v in analysis_tasks.items():
#     print(f'exporting analysis for `{k}`...')

#     file_out_name = k
#     file1 = v[0][0]
#     file2 = v[0][1]
#     labels = v[1]

#     ''' Bar chart, summary table and buswise values '''
#     if v[3][1]:
#         visualize_datasets(file1, file2, labels = labels, file_out = f'bar_{file_out_name}.pdf', 
#                         colors=["#FFFFFF", "#808080"],
#                         hatches=["", ""], do_show=False)

#     t1, t2 = compare_datasets(file1, file2, labels = labels, include_summary=True)

#     # table A: summary
#     if t2:
#         if v[3][0]:
#             with open(os.path.join(tables_dir, f"table_{file_out_name}A.tex"), "w") as f:
#                 f.write(t2)

#     # table B: bus-wise
#     if v[3][2]:
#         with open(os.path.join(tables_dir, f"table_{file_out_name}B.tex"), "w") as f:
#             f.write(t1)

#     # table C: generators loading
#     if v[3][3]:
#         t3 = compare_datasets_S(file1, file2, labels, buses)
#         with open(os.path.join(tables_dir, f"table_{file_out_name}C.tex"), "w") as f:
#             f.write(t3)

# plot_delta_boxplot('4-0.csv', 
#                    ['4-4_095.csv', '4-4_100.csv', '4-4.csv', '4-4_110.csv'], 
#                    ['0.95', '1.00', '1.05', '1.10'],
#                    'box_4-4')

''' heatmap '''
cases = {v[2]: v[0] for k, v in analysis_tasks.items() if k not in ['CI_4-5', 'classic_4-5']}
file_out_name = 'heatmap'
plot_error_heatmap(cases, file_out = f'{file_out_name}.pdf')


# ''' time series analysis '''
# file = 'timeseries_14bus.csv'
# file_out = 'timeseries'
# buses = ['2', '5', '8', '14']
# visualize_timeseries(file, f'{file_out}.pdf', buses)

# ''' random time series analysis '''
# file = 'random_timeseries_14bus.csv'
# file_out = 'random_timeseries'
# buses = ['2', '5', '8', '14']
# visualize_timeseries(file, f'{file_out}.pdf', buses)
