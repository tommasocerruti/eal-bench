"""Remove the float barrier that leaves page 23 nearly blank, and drop the writer list from the capacity caption and paragraph."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)


def sub1(name, old, new):
    p = ICLR / name
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (name, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("ok", name, old[:50])


t = (ICLR / "multiseed_appendix.tex").read_text(encoding="utf-8")
lines = t.split("\n")
assert lines[126].strip() == B + "FloatBarrier", lines[126]
del lines[126]
(ICLR / "multiseed_appendix.tex").write_text("\n".join(lines), encoding="utf-8", newline="\n")
print("ok multiseed FloatBarrier removed")

sub1("extension_mitigations_appendix.tex",
     "Canonical seed, typed incremental memory, both executors, GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, DeepSeek V4.1 Flash; 512 unauthorized requests per arm.",
     "Canonical seed, typed incremental memory, both executors; 512 unauthorized requests per arm.")
sub1("extension_mitigations_appendix.tex",
     "At the canonical seed with typed incremental memory, both executors, and the four writers whose four arms all completed, capacity is either",
     "At the canonical seed with typed incremental memory and both executors, capacity is either")
print("done")
