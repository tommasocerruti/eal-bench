"""Two corrections to the seed pass.
The pressure appendix claimed the intervention was never replicated across seeds, which is false for finance: the five
original writers were run at three writer seeds there. Only the seed all seven writers share is reported, so say that.
Also drop the two redundant three-seed clauses on the cue sub-figures, since their parent figure now states the split."""
import pathlib
ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92); NL = chr(10)


def sub(name, old, new, count=1):
    p = ICLR / name; t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (name, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n"); print("ok", name, "|", " ".join(old.split())[:60])


sub("transfer_pressure_appendix.tex",
    "Unlike the main three-seed transfer experiment in Appendix~" + B + "ref{app:three-seed-matrix}, this intervention was not replicated across seeds.",
    "We report the one seed each domain shares across all seven writers rather than the three of Appendix~" + B + "ref{app:three-seed-matrix}.")
sub("main.tex", "values indicate fewer authorization errors or more exact memories, pooled over three seeds.}",
    "values indicate fewer authorization errors or more exact memories.}")
sub("main.tex", "higher paired" + NL + "  discrimination, pooled over three seeds.}", "higher paired" + NL + "  discrimination.}")
print("done")
