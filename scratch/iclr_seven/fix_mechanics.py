"""Typos and mechanics from the 2026-09-19 review. Nothing here changes a number, a claim, or a table value."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)


def sub1(name, old, new):
    p = ICLR / name; t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (name, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n"); print("ok", name, old[:50])


sub1("main.tex", B + "paragraph{Understanding and Preventing False Authority.}", B + "paragraph{Understanding and preventing false authority.}")
sub1("main.tex", "after each request and has the writer update memory from it", "after each request and have the writer update memory from it")
sub1("main.tex", "First, " + B + "textit{source-filtering} keeps a typed authorization record", "First, " + B + "textit{source filtering} keeps a typed authorization record")
sub1("main.tex", "Second, a " + B + "textit{event-based memory}", "Second, an " + B + "textit{event-based memory}")
sub1("main.tex", "8 to 16 cases and correspondingly 32--64 request pairs", "8 to 16 cases and correspondingly 32 to 64 request pairs")
sub1("main.tex", B + "paragraph{Estimation, uncertainty, and reproducibility}" + chr(10), B + "paragraph{Estimation, uncertainty, and reproducibility.}" + chr(10))
sub1("main.tex", "with disaggregated values in Appendix Table~", "with exact counts in Appendix Table~")
sub1("main.tex", "using 1.2--3.0 times the writer's input tokens", "using 1.2 to 3.0 times the writer's input tokens")
sub1("transfer_pressure_appendix.tex", "and is unchanged in cybersecurity (Appendix~" + B + "ref{app:full-transfer}).", "and is unchanged in cybersecurity.")
sub1("pressure_prompt_appendix.tex", "the two-sentence message under it.", "the three-sentence message under it.")
sub1("extension_results_appendix.tex", "    authoritative change misapplied & a real grant, revocation, narrowing, or replacement", "    change misapplied & a real grant, revocation, narrowing, or replacement")
p = ICLR / "references.bib"; t = p.read_text(encoding="utf-8")
n = t.count("Frontier LLM Evaluation"); t = t.replace("Frontier LLM Evaluation", "Frontier {LLM} Evaluation"); p.write_text(t, encoding="utf-8", newline="\n"); print("bib LLM protected:", n)
print("done")
