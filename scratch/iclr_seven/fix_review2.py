"""Review items with rulings from 2026-09-19: wording fixes (1, 5, 6, 7, 8, 10, 13, 14, 15, 18, 20), the corrected
seven-writer false-authority counts (item 3; one failure_mechanisms call per run, see pf_added_per_run.py), and the
capacity caption reworded so no sentence starts with a number word."""
import pathlib
ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92); NL = chr(10); PC = B + "%"

def sub(name, old, new, count=1):
    p = ICLR / name; t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (name, old[:80], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n"); print("ok", name, "|", old[:60].replace(NL, " "))

# item 3: corrected false-authority counts
sub("main.tex", "up to 51.3" + PC + " of unauthorized requests", "up to 45.4" + PC + " of unauthorized requests", 2)
sub("main.tex", "the pooled false-authority rate is 27.1" + PC + " in procurement against an unauthorized action rate of 26.6" + PC + ", and the two rates stay within six points of each other in cybersecurity and finance.",
    "the pooled false-authority rate is 25.9" + PC + " in procurement against an unauthorized action rate of 26.6" + PC + ", and the two rates stay within one point of each other in cybersecurity and finance.")
sub("main.tex", "4,614/7,770 (59.4" + PC + ") contain a semantic error and 581/7,770 (7.5" + PC + ") contain an authority-gaining error",
    "4,419/7,770 (56.9" + PC + ") contain a semantic error and 527/7,770 (6.8" + PC + ") contain an authority-gaining error")
sub("main.tex", "request-level false authority is 733/2,772 (26.4" + PC + ").", "request-level false authority is 642/2,772 (23.2" + PC + ").")
sub("main.tex", "    Procurement & 27.1" + PC + " & 26.6" + PC + " " + B + B, "    Procurement & 25.9" + PC + " & 26.6" + PC + " " + B + B)
sub("main.tex", "    Cybersecurity & 13.6" + PC + " & 10.5" + PC + " " + B + B, "    Cybersecurity & 10.5" + PC + " & 10.5" + PC + " " + B + B)
sub("main.tex", "    Finance & 51.3" + PC + " & 45.9" + PC + " " + B + B, "    Finance & 45.4" + PC + " & 45.9" + PC + " " + B + B)
sub("main.tex", "    Domain & false-authority rate & Unauthorized action rate rate " + B + B, "    Domain & False-authority rate & Unauthorized action rate " + B + B)
sub("main.tex", "  false-authority rate is computed deterministically from final typed memory", "  The false-authority rate is computed deterministically from final typed memory")
# item 1: conclusion names the wrong mitigation
sub("main.tex", "source-authority rules remove most laundering in procurement and finance without sacrificing legitimate use but worsen it in cybersecurity, whereas rebuilding memory from history removes most laundering across domains while preserving legitimate actions lost to origin filters.",
    "a writer instruction about authority removes most laundering in procurement and finance without sacrificing legitimate use but worsens it in cybersecurity, source filtering and event sourcing remove most laundering in procurement and finance at a large cost in legitimate actions and give no gain in cybersecurity, whereas rebuilding memory from history removes most laundering across domains while preserving the legitimate actions lost to origin filters.")
# item 13
sub("main.tex", "All writers and executors pass model inclusion criteria in Section", "All executors pass model inclusion criteria in Section")
# item 14
sub("main.tex", "A single write-back has no effect, and the loss accumulates over rounds", "Writing the actions back once, without further rounds, has no effect, and the loss accumulates over rounds")
sub("main.tex", "whereas the unauthorized action rate barely moves and finance is unaffected in both arms", "whereas the unauthorized action rate rises by under three points and finance is unaffected in both arms")
sub("main.tex", "while the unauthorized action rate barely moves.", "while the unauthorized action rate rises by under three points.")
# item 15
sub("main.tex", "is the least safe condition throughout, reaching", "is the least safe of the four memory conditions in every domain, reaching")
# item 5
sub("extension_results_appendix.tex", "whether the change amends the grant in place or revokes it and issues a replacement",
    "whether the change amends the grant in place, revokes it and issues an explicit replacement, or revokes it and issues an implicit one")
sub("extension_results_appendix.tex", "(false-authority rate 18.5" + PC + " against 6.4" + PC + ")", "(false-authority rate 18.5" + PC + " against 6.4" + PC + ", with 8.1" + PC + " for explicit and 4.8" + PC + " for implicit replacements)")
# item 6
sub("extension_results_appendix.tex", "Because the benchmark histories are written by hand, the features", "Because the benchmark histories were authored case by case, the features")
# item 20
sub("extension_results_appendix.tex", "with 95" + PC + " bootstrap intervals over chains; both executors, canonical seed.}",
    "with 95" + PC + " bootstrap intervals over chains; both executors, canonical seed. Round 0 is a fresh writer sample at the canonical seed inside the closed-loop runs, so it differs slightly from the writer-route tables.}")
# item 7: stale Grok paragraph
sub("transfer_pressure_appendix.tex", NL + "Within Grok pressure replays, pooled unauthorized action rate is 11/256" + NL + "(4.3" + PC + "). The free-text incremental and typed one-shot rates are 2/64 (3.1" + PC + ")" + NL + "and 4/64 (6.2" + PC + ") pooled across executors; the corresponding DeepSeek-only" + NL + "rates are 2/32 (6.2" + PC + ") and 4/32 (12.5" + PC + ")." + NL, "")
# item 8
sub("source_authority_appendix.tex", "values are percentages, pooling all writers, three seeds, and both executors.}",
    "values are percentages, pooling all writers, three seeds, and both executors. Baseline trials are re-executed within the paired runs, so they differ from the writer-route tables by executor sampling.}")
sub("event_sourcing_appendix.tex", "Values pool all writers, three seeds, and both executors.}",
    "Values pool all writers, three seeds, and both executors. Baseline trials are re-executed within the paired runs, so they differ from the writer-route tables by executor sampling.}")
# item 10
sub("extension_mitigations_appendix.tex", "the rate rises from 18.8" + PC + " to 62.5" + PC + " in one cell.", "the rate rises from 18.8" + PC + " to 62.5" + PC + " in one cell of the design runs at the canonical seed.")
# item 18
sub("extension_mitigations_appendix.tex", "and never rebuilding leaves 38.0" + PC + " (one seed).", "and never rebuilding leaves 38.0" + PC + " (one seed, so the last two cells lie within single-seed variation).")
# capacity caption: no number word at sentence start
sub("capacity_ablation_appendix.tex", "Five writers (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, Qwen-Plus), GPT-OSS-120B as executor, one seed.",
    "The writers are GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, and Qwen-Plus, with GPT-OSS-120B as executor and one seed.")
print("done")
