"""Second styling pass: printed text of about 7 pt for ticks and 7.5 pt for labels (the first pass at 8 pt collided in the
dense three-panel figures), legends moved out of the data, two-line round labels, shorter axis titles."""
import pathlib

ROOT = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench")
B = chr(92)


def patch(path, pairs):
    p = ROOT / path; t = p.read_text(encoding="utf-8")
    for old, new, *count in pairs:
        n = t.count(old); want = count[0] if count else 1
        assert n == want, (path, old[:60], n)
        t = t.replace(old, new)
    p.write_text(t, encoding="utf-8", newline="\n"); print("patched", path)


# closed loop (scale 0.733): ticks 9.5, labels 10, legend 9, titles 10.5; two-line round labels; legend below the panels
patch("analysis/plot_closed_loop_figure.py", [
    ('"font.size": 11, "axes.titlesize": 11.5, "axes.labelsize": 11,', '"font.size": 10, "axes.titlesize": 10.5, "axes.labelsize": 10,'),
    ('"xtick.labelsize": 10.5, "ytick.labelsize": 10.5, "legend.fontsize": 10.5,', '"xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 9.5,'),
    ('loc="left", fontsize=11.5, pad=4)', 'loc="left", fontsize=10.5, pad=4)'),
    ('ax_bot.set_xticklabels(["open loop" if r == 0 else f"round {r}" for r in rounds])', 'ax_bot.set_xticklabels(["open" + chr(10) + "loop" if r == 0 else "round" + chr(10) + str(r) for r in rounds])'),
    ('            ax_top.legend(frameon=False, loc="lower left", handlelength=1.8)', '            fig.legend(*ax_top.get_legend_handles_labels(), frameon=False, loc="lower center", ncol=2, handlelength=1.8, bbox_to_anchor=(0.5, -0.02))'),
    ('outer = fig.add_gridspec(1, 3, wspace=0.32, left=0.075, right=0.99, top=0.86, bottom=0.17)', 'outer = fig.add_gridspec(1, 3, wspace=0.34, left=0.085, right=0.99, top=0.88, bottom=0.24)'),
])
# compute figure (scale 0.764): ticks 9, labels 9.5, titles 10, legends 8; more room between panels; legends out of the data
patch("scratch/iclr_seven/fig_ttc_seven.py", [
    ('"font.size": 10.5, "axes.labelsize": 10.5, "xtick.labelsize": 10, "ytick.labelsize": 10,', '"font.size": 9.5, "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,'),
    ('loc="left", fontsize=11)', 'loc="left", fontsize=10)', 3),
    ('gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], hspace=0.12, wspace=0.42)', 'gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], hspace=0.12, wspace=0.55)'),
    ('b.set_ylim(0, 65);', 'b.set_ylim(0, 75);'),
    ('b.legend(frameon=False, fontsize=9.5, loc="lower right")', 'b.legend(frameon=False, fontsize=8, loc="upper left")'),
    ('c.set_ylim(0, 80);', 'c.set_ylim(0, 100);'),
    ('c.legend(frameon=False, fontsize=9.5, loc="upper right")', 'c.legend(frameon=False, fontsize=8, loc="upper right")'),
])
# restatement figure (scale 0.764): same sizes; shorter x title; legend in panel B where the upper left is empty
patch("scratch/iclr_seven/fig_restatement.py", [
    ('"font.size": 10.5, "axes.labelsize": 10.5, "xtick.labelsize": 10, "ytick.labelsize": 10,', '"font.size": 9.5, "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,'),
    ('loc="left", fontsize=11)', 'loc="left", fontsize=10)', 3),
    ('ax.set_xlabel("Later restatements of the superseded permission")', 'ax.set_xlabel("Later restatements")'),
    ('axes[0].legend(frameon=False, fontsize=9.5, loc="upper left")', 'axes[1].legend(frameon=False, fontsize=8, loc="upper left")'),
])
# cue figures (scale 0.733): ticks 8.5, labels 9, titles 10, legend 9; shorter x title
patch("scratch/iclr_seven/plot_cue_seven.py", [
    ('            "font.size": 11,\n            "axes.titlesize": 11.5,\n            "axes.labelsize": 11,\n            "xtick.labelsize": 10.5,\n            "ytick.labelsize": 10.5,\n            "legend.fontsize": 10.5,',
     '            "font.size": 9.5,\n            "axes.titlesize": 10,\n            "axes.labelsize": 9,\n            "xtick.labelsize": 8.5,\n            "ytick.labelsize": 8.5,\n            "legend.fontsize": 9,'),
    ('loc="left", fontsize=11.5, pad=8)', 'loc="left", fontsize=10, pad=8)', 4),
    ('                    fontsize=11,', '                    fontsize=9.5,'),
    ('    ax.set_xlabel("Improvement (percentage points)")', '    ax.set_xlabel("Improvement (pp)")'),
])
print("done")
