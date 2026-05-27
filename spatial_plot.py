import matplotlib.pyplot as plt
import networkx as nx
import os
import numpy as np
import matplotlib.colors as mcolors
import csv

reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
images_dir = os.path.join(os.path.dirname(__file__), 'images')

# --- Bus coordinates ---
bus_coords_orig = {
    1: (534.9933774834437, 2069.1655629139073),
    2: (1518.4370860927152, 3422.3841059602646),
    3: (4259.867549668874, 4232.741721854304),
    4: (4259.867549668874, 2777.245033112583),
    5: (2505.4039735099336, 2588.4238410596026),
    6: (2521.139072847682, 2029.8278145695363),
    7: (4840.82119205298, 2320.927152317881),
    8: (5249.933774834437, 2320.927152317881),
    9: (4354.278145695364, 1903.9470198675497),
    10: (3654.066225165563, 1597.112582781457),
    11: (3174.1456953642382, 1463.364238410596),
    12: (1702.9139072847684, 1156.5298013245033),
    13: (2513.271523178808, 794.6225165562913),
    14: (3559.6556291390725, 1117.1920529801323)
}

img_height = 4649  # image height
bus_coords = {k: (x, img_height - y) for k, (x, y) in bus_coords_orig.items()}

# --- Line connectivity ---
lines = [
    (1,2), (2,3), (2,4), (3,4), (2,5), (4,5), (1,5),
    (5,6), (4,9), (4,7), (7,8), (7,9), (2,4), (9,10), 
    (9,14), (6,11), (6,12), (6,13), (10,11), (12,13), 
    (13,14), 
]

ADDIN_DEFAULTS = {
    "color":  "none",
    "shape":  "o",
    "size":   150,
    "alpha":  1,
}

def plot_network_error(file1: str, file2: str, bus_coords: dict, lines: list, addins: list, disc_marker: list, save_path: str = None):

    def load_csv(file):
        buses, values = [], []
        with open(os.path.join(reports_dir, file), newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                buses.append(int(row['bus']))
                values.append(float(row['I_SCC_mag']))
        return buses, np.array(values)

    buses, v1 = load_csv(file1)
    _,     v2 = load_csv(file2)

    pct_err = (v2 - v1) / v1 * 100
    err_by_bus = dict(zip(buses, pct_err))

    # --- build graph ---
    G = nx.Graph()
    G.add_nodes_from(buses)
    G.add_edges_from(lines)

    node_colors = [err_by_bus.get(n, 0) for n in G.nodes()]
    limit = np.abs(pct_err).max()
    norm  = mcolors.TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)

    fig, ax = plt.subplots(figsize=(7, 3.5))

    nx.draw_networkx_edges(G, bus_coords, ax=ax, edge_color="gray", width=0.75)

    nodes = nx.draw_networkx_nodes(G, bus_coords, ax=ax,
                                node_color=node_colors,
                                cmap="RdBu",
                                node_size=400,
                                vmin=-limit, vmax=limit,
                                edgecolors="black",
                                linewidths=1.0)

    nx.draw_networkx_labels(G, bus_coords, ax=ax, font_size=8)

    # --- decorative add-ins ---
    all_addin_pos = {}
    for a in addins:
        all_addin_pos.update(a["nodes"])

    for a in addins:
        color = a.get("color", ADDIN_DEFAULTS["color"])
        shape = a.get("shape", ADDIN_DEFAULTS["shape"])
        size  = a.get("size",  ADDIN_DEFAULTS["size"])
        alpha = a.get("alpha", ADDIN_DEFAULTS["alpha"])

        # edges first
        nx.draw_networkx_edges(G, {**bus_coords, **all_addin_pos},
                            edgelist=a["edges"],
                            ax=ax,
                            edge_color="black",
                            width=0.75,
                            style="dotted",
                            alpha=0.5)
        # nodes on top
        nx.draw_networkx_nodes(G, a["nodes"], nodelist=list(a["nodes"].keys()),
                            ax=ax,
                            node_color=color,
                            node_shape=shape,
                            node_size=size,
                            alpha=alpha,
                            edgecolors="gray",
                            linewidths=0.5)
        nx.draw_networkx_labels(G, a["nodes"],
                                labels={k: a["label"] for k in a["nodes"].keys()},
                                ax=ax,
                                font_size=7,
                                font_color="white")
    # --------------------------

    sm = plt.cm.ScalarMappable(cmap="RdBu", norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, label=r"$\Delta$ (%)")

    ax.set_title(r"Short-circuit $\Delta$ (%)")
    ax.axis("off")
    
    if disc_marker is not None:
        for x, y in disc_marker:  
            plt.text(x, y, 'X', fontsize=10, ha='center', va='center', color='red')
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, format="pdf", bbox_inches="tight")
    plt.show()


addins_3_2 = [
    {
        "nodes":  {15: (bus_coords[2][0], bus_coords[2][1]-750)},
        "edges":  [(2, 15)],
        "label":  "G",
        "color": "grey",
    },
    {
        "nodes":  {16: (bus_coords[12][0], bus_coords[12][1]+750)},
        "edges":  [(12, 16)],
        "label":  "G",
        "color": "grey",
    },
    {
        "nodes":  {17: (bus_coords[13][0], bus_coords[13][1]+750)},
        "edges":  [(13, 17)],
        "label":  "G",
        "color": "grey",
    },
    {
        "nodes":  {18: (bus_coords[14][0], bus_coords[14][1]+750)},
        "edges":  [(14, 18)],
        "label":  "G",
        "color": "grey",
    },
]

disc_marker_3_2 = [
    (bus_coords[2][0], bus_coords[2][1]-375), 
    (bus_coords[12][0], bus_coords[12][1]+375), 
    (bus_coords[13][0], bus_coords[13][1]+375), 
    (bus_coords[14][0], bus_coords[14][1]+375)
]

addins_4_2 = [
    {
        "nodes":  {16: (bus_coords[12][0], bus_coords[12][1]+750)},
        "edges":  [(12, 16)],
        "label":  "FC",
        "color": "orange",
        "size": 300,
    },
]

plot_network_error("3-0.csv",  "3-2.csv", bus_coords, lines, addins_3_2, disc_marker_3_2, os.path.join(images_dir, 'spatial_3-2.pdf'))
plot_network_error("4-2A.csv",  "4-2B.csv", bus_coords, lines, addins_4_2, None, os.path.join(images_dir, 'spatial_4-2.pdf'))