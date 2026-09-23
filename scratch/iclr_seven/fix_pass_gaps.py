"""Two gaps found in the main-versus-appendix pass: the 5.4% surviving false-authority rate quoted in Section 4.6 had
no counts anywhere in the appendix, and '164 executor-only replays' reads as a request count when it is a run count."""
import pathlib
ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92); PC = B + "%"


def sub(name, old, new, count=1):
    p = ICLR / name; t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (name, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n"); print("ok", name, "|", " ".join(old.split())[:60])


sub("source_authority_appendix.tex",
    "The gate changes nothing in cybersecurity because none of the records there cites a source it would reject, and the representation-level effect of Table~" + B + "ref{tab:source-authority-full} therefore comes entirely from procurement and finance.",
    "The gate changes nothing in cybersecurity because none of the records there cites a source it would reject, and the representation-level effect of Table~" + B + "ref{tab:source-authority-full} therefore comes entirely from procurement and finance. "
    "Over the same three-seed population, 149 of 2,772 unauthorized probes (5.4" + PC + ") are still authorized by gated memory, almost all of them in cybersecurity, because a record can cite an authorized grantor and still misrepresent scope, validity, or revocation state.")
sub("multiseed_appendix.tex", "164 executor-only replays in all", "164 executor-only replay runs in all")
print("done")
