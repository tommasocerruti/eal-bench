"""Remove the last original/added-writer phrasing and the writer count in the capacity appendix."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(name, old, new):
    p = ICLR / name
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (name, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("ok", name, old[:50])


sub1("main.tex", ", the two added writers and a third executor, the generated histories,", ", a third executor, the generated histories,")
sub1("capacity_ablation_appendix.tex", "We hold fixed the twelve cases, five writers, seed,", "We hold fixed the twelve cases, the writers, the seed,")
sub1("extension_results_appendix.tex", "% Appendix subsections: the two added writers and a third executor, the generated",
     "% Appendix subsections: a third executor, the generated")
print("done")
