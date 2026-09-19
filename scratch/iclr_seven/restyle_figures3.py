"""Third styling pass. Target printed sizes for every figure: ticks 7 pt, axis labels 7.5, panel titles 8, legends 7.
In-figure sizes are target / (printed width / canvas width). Legends go inside empty regions of the axes."""
import pathlib

ROOT = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench")


def patch(path, pairs):
    p = ROOT / path; t = p.read_text(encoding="utf-8")
    for old, new, *count in pairs:
        n = t.count(old); want = count[0] if count else 1
        assert n == want, (path, old[:60], n)
        t = t.replace(old, new)
    p.write_text(t, encoding="utf-8", newline="\n"); print("patched", path)


# closed loop: 7.5 in canvas at linewidth (5.5 in): scale 0.733 -> ticks 9.5, labels 10.2, titles 11, legend 9.5; legend inside panel C
patch("analysis/plot_closed_loop_figure.py", [
    ('"font.size": 10, "axes.titlesize": 10.5, "axes.labelsize": 10,', '"font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10.2,'),
    ('"xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 9.5,', '"xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 9.5,'),
    ('loc="left", fontsize=10.5, pad=4)', 'loc="left", fontsize=11, pad=4)'),
    ('            fig.legend(*ax_top.get_legend_handles_labels(), frameon=False, loc="lower center", ncol=2, handlelength=1.8, bbox_to_anchor=(0.5, -0.02))', '            pass'),
    ('outer = fig.add_gridspec(1, 3, wspace=0.34, left=0.085, right=0.99, top=0.88, bottom=0.24)', 'outer = fig.add_gridspec(1, 3, wspace=0.34, left=0.085, right=0.99, top=0.88, bottom=0.18)'),
])
# the legend goes into the finance panel, whose lines are flat at the top and bottom
p = ROOT / "analysis/plot_closed_loop_figure.py"; t = p.read_text(encoding="utf-8")
anchor = '        ax_top.set_title(r"$\\bf{" + "ABC"[col] + "}$  " + DOMAIN_TITLE[dom], loc="left", fontsize=11, pad=4)'
assert t.count(anchor) == 1
t = t.replace(anchor, anchor + '\n        if col == 2:\n            ax_top.legend(frameon=False, loc="center", handlelength=1.8)')
p.write_text(t, encoding="utf-8", newline="\n"); print("closed-loop legend in panel C")

# compute figure: 7.2 in canvas at linewidth: scale 0.764 -> ticks 9.2, labels 9.8, titles 10.5, legend 9; legends in empty corners
patch("scratch/iclr_seven/fig_ttc_seven.py", [
    ('"font.size": 9.5, "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,', '"font.size": 9.5, "axes.labelsize": 9.8, "xtick.labelsize": 9.2, "ytick.labelsize": 9.2,'),
    ('loc="left", fontsize=10)', 'loc="left", fontsize=10.5)', 3),
    ('b.legend(frameon=False, fontsize=8, loc="upper left")', 'b.legend(frameon=False, fontsize=9, loc="lower right")'),
    ('c.legend(frameon=False, fontsize=8, loc="upper right")', 'c.legend(frameon=False, fontsize=9, loc="upper right")'),
])
# restatement figure: same canvas and scale
patch("scratch/iclr_seven/fig_restatement.py", [
    ('"font.size": 9.5, "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,', '"font.size": 9.5, "axes.labelsize": 9.8, "xtick.labelsize": 9.2, "ytick.labelsize": 9.2,'),
    ('loc="left", fontsize=10)', 'loc="left", fontsize=10.5)', 3),
    ('axes[1].legend(frameon=False, fontsize=8, loc="upper left")', 'axes[1].legend(frameon=False, fontsize=9, loc="upper left")'),
])
# mechanism figure: 5.5 in canvas at linewidth: true size -> ticks 7, labels 7.5, legend 7
patch("scratch/iclr_seven/fig_mechanism.py", [
    ('"font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,', '"font.size": 7.5, "axes.labelsize": 7.5, "xtick.labelsize": 7, "ytick.labelsize": 7,'),
    ('va="center", ha="left", fontsize=8, color="#444444")', 'va="center", ha="left", fontsize=7, color="#444444")'),
    ('ncol=3, frameon=False, fontsize=8, handlelength=1.2, columnspacing=1.4)', 'ncol=3, frameon=False, fontsize=7, handlelength=1.2, columnspacing=1.4)'),
])
# frontier: 4.0 x 3.0 in canvas printed at 0.72 linewidth (3.96 in): true size -> ticks 7, labels 7.5, annotations 7, legend 7 inside lower right
patch("scratch/iclr_seven/fig4_final.py", [
    ('"font.size": 10, "axes.labelsize": 10.5, "legend.fontsize": 10.5,', '"font.size": 7.5, "axes.labelsize": 7.5, "legend.fontsize": 7,'),
    ('fig, ax = plt.subplots(figsize=(3.9, 3.1))', 'fig, ax = plt.subplots(figsize=(4.0, 3.0))'),
    ('xytext=(dx, dy), ha=ha, fontsize=9, color="#222222")', 'xytext=(dx, dy), ha=ha, fontsize=7, color="#222222")'),
    ('xytext=(7, -14), ha="left", fontsize=9, color="#222222")', 'xytext=(7, -12), ha="left", fontsize=7, color="#222222")'),
    ('ax.tick_params(axis="both", labelsize=10)', 'ax.tick_params(axis="both", labelsize=7)'),
    ('"[lower = more safety]", fontsize=10.5)', '"[lower = more safety]", fontsize=7.5)'),
    ('"[higher = more utility]", fontsize=10.5)', '"[higher = more utility]", fontsize=7.5)'),
    ('ax.legend(handles=handles, frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=1, fontsize=10.5, handlelength=1.4, handletextpad=0.6, labelspacing=0.9, borderaxespad=0.0)',
     'ax.legend(handles=handles, frameon=False, loc="lower right", ncol=1, fontsize=7, handlelength=1.3, handletextpad=0.6, labelspacing=0.7, borderaxespad=0.6)'),
])
# cue figures: 7.5 in canvases at linewidth: scale 0.733 -> ticks 9.5, labels 10.2, titles 11, legend 9.5
patch("scratch/iclr_seven/plot_cue_seven.py", [
    ('            "font.size": 9.5,\n            "axes.titlesize": 10,\n            "axes.labelsize": 9,\n            "xtick.labelsize": 8.5,\n            "ytick.labelsize": 8.5,\n            "legend.fontsize": 9,',
     '            "font.size": 10,\n            "axes.titlesize": 11,\n            "axes.labelsize": 10.2,\n            "xtick.labelsize": 9.5,\n            "ytick.labelsize": 9.5,\n            "legend.fontsize": 9.5,'),
    ('loc="left", fontsize=10, pad=8)', 'loc="left", fontsize=11, pad=8)', 4),
    ('                    fontsize=9.5,', '                    fontsize=10.2,'),
])
print("done")
