"""Post-pipeline corrections: closed-loop numbers without the duplicate Grok run (42 two-arm runs, 504 chains),
real-grant counts over all writers, rebuild wording that matches the pooled cells, and one caption."""
import os
import pathlib

ICLR = pathlib.Path(os.environ.get("ICLR_DIR", r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr"))
B = chr(92)


def sub1(name, old, new):
    p = ICLR / name
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (name, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("ok", name, old[:50])


R = B + "ref"
# main text
sub1("main.tex", "lowers legitimate actions by 11 points over three rounds", "lowers legitimate actions by 14 points over three rounds")
sub1("main.tex", "the legitimate action rate at round 3 is 10.7 points below the control", "the legitimate action rate at round 3 is 14.3 points below the control")
sub1("main.tex", "and it lowers the unauthorized action rate in every domain with no loss of legitimate actions (Section~" + R + "{sec:memory-design-results}).",
     "and it lowers the unauthorized action rate in every domain while the legitimate action rate rises or stays within a point of the baseline (Section~" + R + "{sec:memory-design-results}).")
# closed-loop appendix
sub1("extension_results_appendix.tex",
     "Paired over all 520 chains at round 3, the legitimate action rate in the action arm is 10.7 points below the control (95" + B + "% CI $-14.6$ to $-6.9$) and the unauthorized action rate 2.6 points above it (95" + B + "% CI $+0.6$ to $+4.5$). The loss builds over rounds, from 2.0 points at round 1 to 7.9 at round 2 and 10.7 at round 3,",
     "Paired over all 504 chains at round 3, the legitimate action rate in the action arm is 14.3 points below the control (95" + B + "% CI $-17.8$ to $-10.8$) and the unauthorized action rate 2.7 points above it (95" + B + "% CI $+0.7$ to $+4.6$). The loss builds over rounds, from 3.8 points at round 1 to 11.4 at round 2 and 14.3 at round 3,")
sub1("extension_results_appendix.tex",
     "Cybersecurity & 240 & 88.8 & 65.4 (60.3--70.3) & 81.9 (76.9--86.5) & 9.7 & 7.5 (5.3--9.9) & 7.2 (4.2--10.5) " + B + B,
     "Cybersecurity & 224 & 87.9 & 62.9 (57.9--67.9) & 87.7 (83.3--91.7) & 10.4 & 7.9 (5.7--10.4) & 7.7 (4.5--11.3) " + B + B)
sub1("extension_results_appendix.tex",
     "Grok 4.3 & 88 & $+2.8$ ($-1.5$, $+7.6$) & $+20.3$ ($+9.8$, $+30.7$) & 8 / 0 " + B + B,
     "Grok 4.3 & 72 & $+3.1$ ($-2.3$, $+8.6$) & $+2.5$ ($-5.3$, $+10.9$) & 7 / 0 " + B + B)
sub1("extension_results_appendix.tex",
     "All & 520 & $+2.6$ ($+0.6$, $+4.5$) & $-10.7$ ($-14.6$, $-6.9$) & 171 / 4 " + B + B,
     "All & 504 & $+2.7$ ($+0.7$, $+4.6$) & $-14.3$ ($-17.8$, $-10.8$) & 171 / 4 " + B + B)
sub1("extension_results_appendix.tex",
     "the final memories hold 4.5 real, active permission records per chain against 7.8 in the frozen starting memory and 6.5 in the control",
     "the final memories hold 4.4 real, active permission records per chain against 7.8 in the frozen starting memory and 5.8 in the control")
sub1("extension_results_appendix.tex",
     B + "caption{" + B + "added{" + B + "textbf{The four labels a judge can give the writer's error at the block where the failure entered.}}}",
     B + "caption{" + B + "added{" + B + "textbf{The four labels a judge can give the writer's error at the failing block.}}}")
# writer-side designs appendix
sub1("extension_mitigations_appendix.tex",
     "Rebuilding lowers the unauthorized action rate in every domain and raises the legitimate action rate (Table~" + R + "{tab:writer-side-mitigations}), and it is the one design change that holds across writers.",
     "Rebuilding lowers the unauthorized action rate in every domain and raises the legitimate action rate in procurement and cybersecurity, with finance within a point of its near-ceiling baseline (Table~" + R + "{tab:writer-side-mitigations}), and it is the one design change that holds across writers.")
print("fix_dedup done")
