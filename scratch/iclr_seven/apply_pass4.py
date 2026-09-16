"""Pass 4: appendix wording to the paper's rules (no clipped sentences, no abstract 'cost', no 'Overall,'),
and a check that no colour macro sits inside a table."""
import pathlib
import re

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


def resub1(text, pattern, new, label):
    m = re.findall(pattern, text)
    assert len(m) == 1, f"{label}: expected 1 regex match, found {len(m)}"
    return re.sub(pattern, new, text)


p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "the executor study replays frozen memories behind GPT-OSS and DeepSeek. Overall, the analysis contains 7,200 cue-paired behavioral units and 360 typed-memory cue triplets.",
         "\\revised{the executor study replays frozen memories behind GPT-OSS and DeepSeek, so the analysis contains 7,200 cue-paired behavioral units and 360 typed-memory cue triplets.}", "overall")
s = sub1(s, "Executor-side effects are smaller. Across ten frozen writer-memory--executor combinations, the generic cue changes",
         "\\revised{Executor-side effects are smaller: across ten frozen writer-memory--executor combinations,} the generic cue changes", "executor-side")
s = resub1(s, r"the tested targets\. These summarize heterogeneity, not population-level\s+uncertainty\.",
           "the tested targets, \\\\revised{summarizing heterogeneity rather than population-level uncertainty}.", "heterogeneity caption")
s = resub1(s, r"bootstrap intervals\. Positive values indicate\s+improvement\.",
           "bootstrap intervals, \\\\revised{with positive values indicating improvement}.", "positive values caption")
p.write_text(s, encoding="utf-8", newline="\n")

# token-count sentence: wherever it sits
hits = []
for f in sorted(ICLR.glob("*.tex")):
    t = f.read_text(encoding="utf-8")
    pat = r"\.\s+Token counts use the benchmark's\s+reference tokenizer\."
    if re.search(pat, t):
        t = re.sub(pat, ", \\\\revised{and token counts use the benchmark's reference tokenizer}.", t, count=1)
        f.write_text(t, encoding="utf-8", newline="\n"); hits.append(f.name)
print("token-count sentence fixed in:", hits)

p = ICLR / "deployment_realism_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "The domains differ in more than wording. Procurement requires", "\\revised{The domains differ in more than wording, because} Procurement requires", "domains differ")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "event_sourcing_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "2,258 alignment rows remain explicitly ambiguous. No LLM judge is used. The event writer sees",
         "2,258 alignment rows remain explicitly ambiguous\\revised{, and no LLM judge is used}. The event writer sees", "no judge")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "so part of the decline there is the cost of any repeated update, and only the paired difference isolates",
         "so part of the decline there follows from repeated updating alone, and only the paired difference isolates", "cost 1")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "removes most laundering in procurement and finance at no cost in legitimate action rate, and doubles it in cybersecurity.}",
         "removes most laundering in procurement and finance with the legitimate action rate unchanged, and doubles it in cybersecurity.}", "cost 2")
s = sub1(s, "and each rebuild reads the whole history, so its cost grows with the history.", "and each rebuild reads the whole history, so its running time grows with the history.", "cost 3")
s = sub1(s, "and all of it in finance at the cost of most legitimate actions, and changes nothing", "and all of it in finance while removing most legitimate actions, and changes nothing", "cost 4")
p.write_text(s, encoding="utf-8", newline="\n")

# colour macros inside tabular environments
bad = []
for f in sorted(ICLR.glob("*.tex")):
    t = f.read_text(encoding="utf-8")
    for chunk in t.split("\\begin{tabular")[1:]:
        body = chunk.split("\\end{tabular")[0]
        if "\\added{" in body or "\\revised{" in body:
            bad.append((f.name, body[:60].replace("\n", " ")))
print("colour inside tables:", bad if bad else "none")
print("pass 4 applied")
