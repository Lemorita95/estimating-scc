import matplotlib.pyplot as plt
import matplotlib as mpl
from cycler import cycler

COLORS  = ["#000000", "#404040", "#808080", "#B0B0B0", "#D0D0D0"]
MARKERS = ["o", "s", "^", "D", "v"]
LINES   = ["-", "--", "-.", ":", (0, (3,1,1,1))]
HATCHES = ["", "...", "///", "xxx", "---"]

SINGLE_COL = 3.5
DOUBLE_COL = 7.16

full_cycle = (
    cycler(color=COLORS[::-1]) +
    cycler(linestyle=LINES) +
    cycler(marker=MARKERS)
)


def set_plot_style():
    plt.rcParams.update({
        # Font
        "font.family":          "serif",
        "font.serif":           ["Times New Roman"],
        "mathtext.fontset":     "cm",
        "font.size":            8,
        "axes.labelsize":       8,
        "axes.titlesize":       8,
        "legend.fontsize":      7,
        "xtick.labelsize":      7,
        "ytick.labelsize":      7,

        # styling cycle
        "axes.prop_cycle": full_cycle,

        # Lines & frame
        "lines.linewidth":      1.2,
        "axes.linewidth":       0.8,

        # Grid
        "axes.grid":            True,
        "grid.linestyle":       "--",
        "grid.linewidth":       0.5,
        "grid.alpha":           0.35,

        # Spines
        "axes.spines.top":      False,
        "axes.spines.right":    False,

        # Legend
        "legend.framealpha":    1.0,
        "legend.edgecolor":     "0.8",

        # Ticks
        "xtick.direction":      "in",
        "ytick.direction":      "in",
        # "xtick.minor.visible":  True,
        "ytick.minor.visible":  True,

        # Saving
        "savefig.dpi":          300,
        "savefig.bbox":         "tight",
        "savefig.format":       "pdf",
    })