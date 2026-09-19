"""One font (DejaVu Sans, as in the closed-loop figure) and printed text of about 8 pt in every paper figure. Each script's
font sizes are scaled by the ratio between its canvas width and the width it is printed at, so that ticks, labels, legends
and panel titles come out the same size on the page. Also removes the change-tracking macro definitions from main.tex and
sets the includegraphics widths the scaling assumes."""
import pathlib
import re

ROOT = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench")
ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
FONT = '"font.family": "DejaVu Sans", "mathtext.fontset": "dejavusans"'


def patch(path, pairs):
    p = ROOT / path; t = p.read_text(encoding="utf-8")
    for old, new, *count in pairs:
        n = t.count(old); want = count[0] if count else 1
        assert n == want, (path, old[:60], n)
        t = t.replace(old, new)
    p.write_text(t, encoding="utf-8", newline="\n"); print("patched", path)


# printed 8 pt at scale 5.5/7.5 = 0.733 -> 11 pt in the figure
patch("analysis/plot_closed_loop_figure.py", [
    ('"font.family": "DejaVu Sans", "font.size": 7.5, "axes.titlesize": 8.5, "axes.labelsize": 7.5,',
     '"font.family": "DejaVu Sans", "mathtext.fontset": "dejavusans", "font.size": 11, "axes.titlesize": 11.5, "axes.labelsize": 11,'),
    ('"xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 6.7, "axes.linewidth": 0.7,',
     '"xtick.labelsize": 10.5, "ytick.labelsize": 10.5, "legend.fontsize": 10.5, "axes.linewidth": 0.7,'),
    ('loc="left", fontsize=9, pad=4)', 'loc="left", fontsize=11.5, pad=4)'),
])
# printed 8 pt at scale 5.5/7.2 = 0.764 -> 10.5 pt
patch("scratch/iclr_seven/fig_ttc_seven.py", [
    ('plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"], "font.size": 8,',
     'plt.rcParams.update({' + FONT + ', "font.size": 10.5, "axes.labelsize": 10.5, "xtick.labelsize": 10, "ytick.labelsize": 10,'),
    ('loc="left", fontsize=9)', 'loc="left", fontsize=11)', 3),
    ('b.legend(frameon=False, fontsize=6.8, loc="lower right")', 'b.legend(frameon=False, fontsize=9.5, loc="lower right")'),
    ('c.legend(frameon=False, fontsize=6.8, loc="upper right")', 'c.legend(frameon=False, fontsize=9.5, loc="upper right")'),
])
patch("scratch/iclr_seven/fig_restatement.py", [
    ('plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"], "font.size": 8,',
     'plt.rcParams.update({' + FONT + ', "font.size": 10.5, "axes.labelsize": 10.5, "xtick.labelsize": 10, "ytick.labelsize": 10,'),
    ('loc="left", fontsize=9)', 'loc="left", fontsize=11)', 3),
    ('axes[0].legend(frameon=False, fontsize=7, loc="upper left")', 'axes[0].legend(frameon=False, fontsize=9.5, loc="upper left")'),
])
# printed at linewidth with a 5.5 in canvas -> true size
patch("scratch/iclr_seven/fig_mechanism.py", [
    ('plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"], "font.size": 8,',
     'plt.rcParams.update({' + FONT + ', "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,'),
    ('ax.text(101, i, f"n = {t:,}", va="center", ha="left", fontsize=7, color="#444444")', 'ax.text(101, i, f"n = {t:,}", va="center", ha="left", fontsize=8, color="#444444")'),
    ('ncol=3, frameon=False, fontsize=7, handlelength=1.2, columnspacing=1.4)', 'ncol=3, frameon=False, fontsize=8, handlelength=1.2, columnspacing=1.4)'),
])
# frontier: 3.6 in canvas plus a side legend (about 4.9 in) printed at 0.72 linewidth = 3.96 in -> scale ~0.8 -> 10 pt for 8 printed
patch("scratch/iclr_seven/fig4_final.py", [
    ('plt.rcParams.update({"font.family": "serif", "font.size": 10, "axes.labelsize": 10, "legend.fontsize": 8.5, "pdf.fonttype": 42, "ps.fonttype": 42,',
     'plt.rcParams.update({' + FONT + ', "font.size": 10, "axes.labelsize": 10.5, "legend.fontsize": 10.5, "pdf.fonttype": 42, "ps.fonttype": 42,'),
    ('fig, ax = plt.subplots(figsize=(4.7, 3.5))', 'fig, ax = plt.subplots(figsize=(3.9, 3.1))'),
    ('xytext=(dx, dy), ha=ha, fontsize=8.5, color="#222222")', 'xytext=(dx, dy), ha=ha, fontsize=9, color="#222222")'),
    ('xytext=(7, -14), ha="left", fontsize=8.5, color="#222222")', 'xytext=(7, -14), ha="left", fontsize=9, color="#222222")'),
    ('ax.tick_params(axis="both", labelsize=11)', 'ax.tick_params(axis="both", labelsize=10)'),
    ('"[lower = more safety]", fontsize=11)', '"[lower = more safety]", fontsize=10.5)'),
    ('"[higher = more utility]", fontsize=11)', '"[higher = more utility]", fontsize=10.5)'),
    ('ax.legend(handles=handles, frameon=False, loc="upper left", bbox_to_anchor=(1.02, 1.0), ncol=1, fontsize=9, handlelength=1.2, handletextpad=0.5, borderaxespad=0.0)',
     'ax.legend(handles=handles, frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=1, fontsize=10.5, handlelength=1.4, handletextpad=0.6, labelspacing=0.9, borderaxespad=0.0)'),
])
# cue figures: 7.5 in canvases printed at linewidth -> 11 pt for 8 printed
patch("scratch/iclr_seven/plot_cue_seven.py", [
    ('            "font.family": "DejaVu Sans",\n            "font.size": 7.5,\n            "axes.titlesize": 9.0,\n            "axes.labelsize": 7.7,\n            "xtick.labelsize": 7.0,\n            "ytick.labelsize": 7.0,\n            "legend.fontsize": 6.7,',
     '            "font.family": "DejaVu Sans",\n            "mathtext.fontset": "dejavusans",\n            "font.size": 11,\n            "axes.titlesize": 11.5,\n            "axes.labelsize": 11,\n            "xtick.labelsize": 10.5,\n            "ytick.labelsize": 10.5,\n            "legend.fontsize": 10.5,'),
    ('loc="left", fontsize=9, pad=8)', 'loc="left", fontsize=11.5, pad=8)', 4),
    ('                    fontsize=8.0,', '                    fontsize=11,'),
])

# main.tex: no macro definitions; widths the scaling assumes
p = ICLR / "main.tex"; t = p.read_text(encoding="utf-8")
lines = t.split(chr(10))
keep = [l for l in lines if not re.match(re.escape(B + "newcommand{" + B) + r"(added|revised|updated)\}", l)]
print("macro definitions removed:", len(lines) - len(keep))
t = chr(10).join(keep)
for old, new in ((B + "includegraphics[width=0.62" + B + "linewidth]{figures/mitigation_pareto_frontier.pdf}", B + "includegraphics[width=0.72" + B + "linewidth]{figures/mitigation_pareto_frontier.pdf}"),
                 ("[width=0.76" + B + "linewidth]{evaluation_cue_appendix_writer_fidelity.pdf}", "[width=" + B + "linewidth]{evaluation_cue_appendix_writer_fidelity.pdf}"),
                 ("[width=0.76" + B + "linewidth]{evaluation_cue_appendix_writer_behavior.pdf}", "[width=" + B + "linewidth]{evaluation_cue_appendix_writer_behavior.pdf}"),
                 ("[width=0.8" + B + "linewidth]{evaluation_cue_appendix_executor_behavior.pdf}", "[width=" + B + "linewidth]{evaluation_cue_appendix_executor_behavior.pdf}")):
    assert t.count(old) == 1, old; t = t.replace(old, new)
p.write_text(t, encoding="utf-8", newline="\n"); print("main.tex widths set")
