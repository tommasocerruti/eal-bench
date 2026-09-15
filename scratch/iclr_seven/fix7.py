import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


old = "\\added{Changing the writer avoids this cost when the change matches the writer's error (Table~\\ref{tab:writer-side-mitigations}). Rebuilding memory from the history every three blocks lowers unauthorized submission in every domain with no loss of authorized use (Section~\\ref{sec:memory-design-results}). Instructing the writer to record only permissions granted by an authorized approver cuts unauthorized submission from 25.4\\% to 5.8\\% in procurement and from 31.7\\% to 1.7\\% in finance with authorized use unchanged, but raises it from 10.4\\% to 21.8\\% in cybersecurity. The judged failures explain the split (Appendix~\\ref{app:diagnosis}): in procurement and finance the writer applies restatements from parties without authority, which the instruction forbids; in cybersecurity the writer fails to record the duty officer's change set, and with the instruction those failed writes nearly double.}"
new = "\\added{Two changes to the writer avoid this cost, but only when they match the error the writer makes (Table~\\ref{tab:writer-side-mitigations}). Rebuilding memory from the history every three blocks lowers unauthorized submission in every domain with no loss of authorized use (Section~\\ref{sec:memory-design-results}). A one-sentence instruction to record only permissions that an authorized approver granted cuts unauthorized submission from 25.4\\% to 5.8\\% in procurement and from 31.7\\% to 1.7\\% in finance, with authorized use unchanged, but raises it from 10.4\\% to 21.8\\% in cybersecurity. The failure labels of Appendix~\\ref{app:diagnosis} explain the split. In procurement and finance nearly every failure is the writer copying a permission restated by someone without authority, which is what the instruction forbids. In cybersecurity nearly every failure is a rejected write of the duty officer's change set, which withdraws permissions, so the old grant stays active in memory; the stricter instruction makes those writes fail more often (376 of 403 failures, against 212 of 216 without it). An instruction helps only where it names the error the writer actually makes.}"
s = sub1(s, old, new, "4.4 paragraph")
s = sub1(s, "\\includegraphics[width=0.42\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "\\includegraphics[width=0.4\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "pareto width")
s = sub1(s, "\\includegraphics[width=0.78\\linewidth]{figures/closed_loop_control.pdf}", "\\includegraphics[width=0.7\\linewidth]{figures/closed_loop_control.pdf}", "closed width")
p.write_text(s, encoding="utf-8", newline="\n")
print("fix7 applied")
