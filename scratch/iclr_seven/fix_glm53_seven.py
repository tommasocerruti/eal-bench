"""Third-executor paragraph after the GLM 5.3 replays of the Grok 4.3 and Qwen-Plus runs (164 replays, seven writers)."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
p = ICLR / "multiseed_appendix.tex"
t = p.read_text(encoding="utf-8")
old = (B + "revised{A third executor, GLM 5.3, replayed the frozen memories of the open-loop extension studies (the memory designs, the generated histories, and the writer instruction with its baselines), 124 executor-only replays in all, so that three executors answer the same requests against the same memories. On the unauthorized action rate the three are interchangeable, within about one point in every replayed cell, and the writer instruction's paired change is the same to the first decimal for all three. The executors differ only on the legitimate action rate in procurement, where GLM 5.3 executes about 10 points fewer legitimate requests and gains correspondingly more from the instruction.}")
new = (B + "updated{A third executor, GLM 5.3, replayed the frozen memories of the open-loop extension studies (the memory designs, the generated histories, and the writer instruction with its baselines), 164 executor-only replays in all, so that three executors answer the same requests against the same memories. On the unauthorized action rate the three are interchangeable: every pooled cell agrees within about two points and most within one, and the writer instruction's paired change agrees across the three to within about half a point in every domain. The executors differ only on the legitimate action rate in procurement, where GLM 5.3 executes 11 to 13 points fewer legitimate requests and gains correspondingly more from the instruction.}")
assert t.count(old) == 1, t.count(old)
p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
print("third-executor paragraph updated")
