"""Frontier caption that explains each defense's position, and the matching sentence in Section 4.6."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
p = ICLR / "main.tex"
t = p.read_text(encoding="utf-8")
i = t.index("  " + B + "caption{" + B + "textbf{Safety--utility Pareto frontier on the exact shared population.}")
j = t.index(chr(10) + "  " + B + "label{fig:mitigation-pareto}", i)
new_caption = ("  " + B + "caption{" + B + "textbf{Safety--utility frontier of the tested defenses.} "
               + B + "updated{Each point pools three domains, seven writers, three seeds, and both executors; fewer unauthorized actions lie to the left and more legitimate actions lie higher, so the best defenses sit toward the upper left. "
               "The two origin checks (squares) lower the unauthorized action rate by restricting what memory may keep, and they pay in legitimate actions: the source-authority gate deletes every record whose cited sources include a message from someone who cannot grant authority, which removes valid grants together with false ones, and bounded event sourcing rebuilds the state from extracted events, so a grant the writer fails to extract never enters it. Both losses are largest in finance. "
               "The writer instruction (red diamond) changes what the writer records rather than what is kept, so it costs almost no legitimate actions, but it removes only the restatement error and therefore leaves cybersecurity untouched. "
               "Rebuilding every three blocks (purple diamond) rewrites the memory from the full history, so it approaches one-shot writing (hollow circle) on both axes and lies above and to the left of the frontier traced by the other four, at 1.2 to 3.0 times the writer's input tokens. "
               "Values are the pooled cells of Tables~" + B + "ref{tab:memory-design-decomposition}, " + B + "ref{tab:source-authority-aligned-domain}, " + B + "ref{tab:event-sourcing-full-behavior}, and~" + B + "ref{tab:writer-side-mitigations}.}}")
t = t[:i] + new_caption + t[j:]
old = "Both pay in legitimate use: the legitimate action rate falls to 53.2" + B + "% under the gate and to 68.6" + B + "% under event sourcing, from 93.1" + B + "% and 93.0" + B + "%.}"
assert t.count(old) == 1, t.count(old)
t = t.replace(old, "Both pay in legitimate use: the legitimate action rate falls to 53.2" + B + "% under the gate and to 68.6" + B + "% under event sourcing, from 93.1" + B + "% and 93.0" + B
              + "%. The gate pays because a valid grant that also cites a colleague's message is deleted with the false ones, and event sourcing pays because a grant the writer fails to extract never enters the state; both losses are largest in finance, where the gate keeps 28" + B + "% of legitimate actions and event sourcing 24" + B + "% (Tables~" + B + "ref{tab:source-authority-aligned-domain} and~" + B + "ref{tab:event-sourcing-full-behavior}).}")
p.write_text(t, encoding="utf-8", newline="\n")
print("caption and 4.6 sentence updated")
