"""Every number inside \\added{} in the three paper files must appear somewhere in the note or the regenerated outputs."""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ICLR = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
REPO = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench")
T = Path(r"C:/Users/mikad/.claude/jobs/e03609a8/tmp/seven")
sources = [REPO / "docs/extension_studies.md", T / "out/proposed_tables.md", T / "out/section7_seeds.md", T / "out/section6_v2.md",
           T / "gate_event.md", T / "cap2.md", T / "seven_summary.json", REPO / "results/analysis/section_cap2.md"]
corpus = ""
for s in sources:
    try:
        corpus += s.read_text(encoding="utf-8", errors="replace") + "\n"
    except FileNotFoundError:
        pass
corpus_norm = corpus.replace(",", "").replace("\u2013", "-").replace("\u2212", "-")


def red_spans(s):
    out = []; i = 0
    while True:
        j = s.find("\\added{", i)
        if j < 0:
            break
        k = j + 7; depth = 1
        while depth and k < len(s):
            depth += (s[k] == "{") - (s[k] == "}"); k += 1
        out.append((s[:j].count("\n") + 1, s[j + 7:k - 1])); i = k
    return out


num_re = re.compile(r"(?<![A-Za-z\\])(\d[\d,]*(?:\.\d+)?)")
for fn in ("main.tex", "extension_results_appendix.tex", "extension_mitigations_appendix.tex"):
    s = (ICLR / fn).read_text(encoding="utf-8")
    missing = {}
    for line, span in red_spans(s):
        txt = re.sub(r"\\(ref|label|cite[pt]?)\{[^}]*\}", " ", span)
        txt = re.sub(r"\$[^$]*\$", lambda m: m.group(0).replace("$", " ").replace("{=}", "="), txt)
        for n in num_re.findall(txt):
            n0 = n.replace(",", "").strip(".")
            if not n0 or n0 in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "95", "2026", "100", "50", "20", "30", "40", "60", "70", "80", "90", "18", "17", "16", "12", "11", "13", "14", "15", "19", "24", "36", "48", "64", "72", "108", "120", "160", "192", "216", "256", "288", "320", "324", "384", "432", "512", "640", "768", "960", "1080", "1920", "4096", "32768", "16384", "2646", "5292"):
                continue
            if n0 not in corpus_norm:
                missing.setdefault(n0, []).append(line)
    print(f"== {fn}: numbers in red text not found in the note or regenerated outputs:")
    for n0, lines in sorted(missing.items(), key=lambda kv: kv[1][0]):
        print(f"   {n0}  (lines {sorted(set(lines))})")
