"""No sentence may begin with a number word, and no caption may end on a hanging word: reword the seed statements."""
import pathlib
ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92); PC = B + "%"; NL = chr(10)


def sub(name, old, new, count=1):
    p = ICLR / name; t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (name, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n"); print("ok", name, "|", " ".join(old.split())[:56])


sub("main.tex", "bootstrap intervals. One seed, procurement only.}", "bootstrap intervals. The study covers procurement at a single seed.}")
sub("main.tex", "indicate fewer authorization errors or more exact memories. Three seeds.}", "indicate fewer authorization errors or more exact memories, pooled over three seeds.}")
sub("main.tex", "higher paired" + NL + "  discrimination. Three seeds.}", "higher paired" + NL + "  discrimination, pooled over three seeds.}")
sub("main.tex", "with positive values indicating improvement. One seed.}", "with positive values indicating improvement at a single seed.}")
sub("extension_results_appendix.tex", "intervals are Wilson 95" + PC + ". One seed; 252 memories and 756 unauthorized requests per row.}",
    "intervals are Wilson 95" + PC + " at a single seed; 252 memories and 756 unauthorized requests per row.}")
sub("event_sourcing_appendix.tex", "so its final-state error is lower. Three seeds, all writers.}",
    "so its final-state error is lower. Rates pool three seeds and all seven writers.}")
sub("capacity_ablation_appendix.tex", "validation failures caused by the capacity bound over all writer updates. One seed.}",
    "validation failures caused by the capacity bound over all writer updates at a single seed.}")
sub("capacity_ablation_appendix.tex", "memory remain in the same resampled cluster. One seed.}", "memory remain in the same resampled cluster at a single seed.}")
sub("main.tex", "the unweighted mean of the three domain rates, computed before rounding.}", "the unweighted mean of the three domain rates, taken before any rounding.}")
print("done")
