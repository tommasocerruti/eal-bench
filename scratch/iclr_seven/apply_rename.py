"""Rename the metrics everywhere (legitimate action rate, unauthorized action rate, false-authority rate),
replace 'provenance' with 'origin' and 'trigger' with 'cause', merge short sentences in the green text,
and cut the contribution list to five two-line items. Exact-match replacements assert a single hit."""
import pathlib
import re

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
FILES = sorted(ICLR.glob("*.tex"))


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


def rename(s):
    # unauthorized submission -> unauthorized action rate
    s = s.replace("unauthorized-submission rates", "unauthorized action rates")
    s = s.replace("unauthorized-submission rate", "unauthorized action rate")
    s = s.replace("unauthorized-submission", "unauthorized-action")
    s = s.replace("Unauthorized submissions", "Unauthorized actions")
    s = s.replace("unauthorized submissions", "unauthorized actions")
    s = s.replace("Unauthorized Submission", "Unauthorized Action Rate")
    s = s.replace("Unauthorized submission", "Unauthorized action rate")
    s = s.replace("unauthorized submission", "unauthorized action rate")
    # authorized use -> legitimate action rate (never touching 'unauthorized use')
    s = re.sub(r"(?<![Uu]n)authorized uses\b", "legitimate actions", s)
    s = re.sub(r"(?<![Uu]n)Authorized Use\b", "Legitimate Action Rate", s)
    s = re.sub(r"(?<![Uu]n)Authorized use\b", "Legitimate action rate", s)
    s = re.sub(r"(?<![Uu]n)authorized use\b", "legitimate action rate", s)
    # abbreviations in tables and captions
    s = re.sub(r"\bAU\b", "LA", s)
    s = re.sub(r"\bUS\b", "UA", s)
    # P(F) and 'formation rate'
    s = s.replace("$P(F)$", "false-authority rate")
    s = s.replace("formation rate", "false-authority rate")
    # provenance -> origin, trigger -> cause
    s = s.replace("Provenance", "Origin").replace("provenance", "origin")
    return s


for f in FILES:
    s = f.read_text(encoding="utf-8")
    s2 = rename(s)
    if s2 != s:
        f.write_text(s2, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ grammar fixes after the mechanical pass
p = ICLR / "main.tex"
s = p.read_text(encoding="utf-8")
# formulation and protocol wording
s = sub1(s, "For authorized requests, \\textbf{legitimate action rate} is the fraction for which the executor takes the requested action, and failures to do so are \\emph{undergrants}; for unauthorized requests, \\textbf{unauthorized action rate} is the fraction for which the executor takes the requested action anyway.",
         "For authorized requests, the \\textbf{legitimate action rate} is the fraction for which the executor takes the requested action, and failures to do so are \\emph{undergrants}; for unauthorized requests, the \\textbf{unauthorized action rate} is the fraction for which the executor takes the requested action anyway. We write the \\textbf{false-authority rate} for $P(F{=}1)$.", "formulation")
s = sub1(s, "achieve 100\\% legitimate action rate and 0\\% unauthorized actions.", "achieve a 100\\% legitimate action rate and a 0\\% unauthorized action rate.", "controls")
s = sub1(s, "We report \\textbf{legitimate action rate} and \\textbf{unauthorized action rate} in all three domains", "We report the \\textbf{legitimate action rate} and the \\textbf{unauthorized action rate} in all three domains", "report")
# abstract
s = sub1(s, "writers create false authority for up to \\added{51.3\\%} of unauthorized requests; once false authority is present, executors act on it in \\added{99.0\\%} of trials.",
         "writers create false authority for up to \\added{51.3\\%} of unauthorized requests, and once false authority is present, executors act on it in \\added{99.0\\%} of trials.", "abstract numbers")
s = sub1(s, "\\revised{The failures trace to one trigger: a later message that repeats a permission the history has since changed. On generated",
         "\\revised{The failures trace to one cause, a later message that repeats a permission the history has since changed. On generated", "abstract cause")
s = sub1(s, "writing the log back into the history erodes legitimate action rate over successive rounds.",
         "writing the log back into the history lowers the legitimate action rate over successive rounds.", "abstract loop")
s = sub1(s, "removes most of the laundering while preserving legitimate action rate, and", "removes most of the laundering while preserving the legitimate action rate, and", "abstract rebuild")
# introduction paragraph: flowing sentences, origin instead of provenance
s = sub1(s, "\\revised{Measuring the failure leaves its cause open. The two origin defenses we test both reduce laundering and both reject legitimate actions, and neither identifies the message the writer misread. We therefore ask what the writer reacts to. The answer differs by domain, and it determines whether a given defense helps, harms, or trades safety for utility.}",
         "\\revised{Measuring how often the failure occurs leaves open what causes it: the two defenses we test that check the origin of each stored record both reduce laundering and both reject legitimate actions, and neither identifies the message the writer misread. We therefore ask what the writer reacts to, and because the answer differs by domain, it determines whether a given defense helps, harms, or trades safety for utility.}", "intro paragraph")
# contributions: five items, two lines each
start = s.index("\\begin{itemize}[leftmargin=0.5cm,topsep=1pt,itemsep=1pt]")
end = s.index("\\end{itemize}", start) + len("\\end{itemize}")
s = s[:start] + """\\begin{itemize}[leftmargin=0.5cm,topsep=1pt,itemsep=1pt]
\\item \\revised{We identify \\textbf{endogenous authorization laundering}, in which an agent's own memory creates authority the history never granted, and separate its formation in memory from its propagation to action.}
\\item \\revised{We introduce \\textbf{\\textsc{EAL-Bench}}, an open-source benchmark that measures how faithfully memory writers preserve evolving authorization state across executors and domains.}
\\item \\revised{False authority forms for up to 51.3\\% of unauthorized requests, propagates to action in 99.0\\% of matched trials, and vanishes under exact-state repair, which localizes the failure to memory.}
\\item \\revised{False authority forms only after a superseded permission is restated without authority; the writer applies the restatement in two domains and loses the legitimate change in the third.}
\\item \\revised{Writing the agent's log back into its history lowers legitimate actions by 18 points over three rounds, and defenses matched to the writer's error avoid the tradeoff that origin checks impose.}
\\end{itemize}""" + s[end:]
# methods
s = sub1(s, "directs the writer to record only permissions that an authorized approver granted (Appendix~\\ref{app:mandate}). The rebuild variant above serves as a fourth. The writer-side comparisons",
         "directs the writer to record only permissions that an authorized approver granted (Appendix~\\ref{app:mandate}), and the rebuild variant above serves as a fourth. The writer-side comparisons", "methods fourth")
# 4.1 / 4.2
s = sub1(s, "Legitimate action rate stays high in the same conditions, so the failures do not reflect a general performance collapse.",
         "The legitimate action rate stays high in the same conditions, so the failures do not reflect a general performance collapse.", "4.1 AU")
s = sub1(s, "\\revised{pooled false-authority rate is 27.1\\% in procurement against 26.6\\% unauthorized action rate, and the two rates stay within six points of each other in cybersecurity and finance}",
         "\\revised{the pooled false-authority rate is 27.1\\% in procurement against an unauthorized action rate of 26.6\\%, and the two rates stay within six points of each other in cybersecurity and finance}", "4.2 rates")
s = sub1(s, "With the erroneous memories, unauthorized action rate occurs in \\added{99.0\\%} of trials;", "With the erroneous memories, an unauthorized action occurs in \\added{99.0\\%} of trials;", "4.2 repair")
s = sub1(s, "\\revised{The trigger can be isolated on generated procurement histories", "\\revised{The cause can be isolated on generated procurement histories", "4.2 cause")
s = sub1(s, "The failure travels with the artifact rather than the executor. Replaying every frozen memory behind both calibrated executors in the three-seed evaluation yields unauthorized action rates within",
         "The failure travels with the artifact rather than the executor. Replaying every frozen memory behind both calibrated executors in the three-seed evaluation yields unauthorized action rates within", "4.3 transfer")
# closed loop
s = sub1(s, "produces the very messages identified above as the trigger, and in deployment", "produces the very messages identified above as the cause, and in deployment", "loop cause")
s = sub1(s, "The damage falls on legitimate work. Legitimate action rate at round 3 is 17.6 points below the control (95\\% CI $-22.0$ to $-13.3$), with the largest loss in cybersecurity, where the executor escalates most often. Unauthorized action rate rises by two points, and finance is unaffected in both arms. A single write-back has no effect; the loss accumulates over rounds (Figure~\\ref{fig:closed-loop}).}",
         "The damage falls on legitimate work rather than on safety: the legitimate action rate at round 3 is 17.6 points below the control (95\\% CI $-22.0$ to $-13.3$), with the largest loss in cybersecurity, where the executor escalates most often, whereas the unauthorized action rate rises by only two points and finance is unaffected in both arms. A single write-back has no effect, and the loss accumulates over rounds (Figure~\\ref{fig:closed-loop}).}", "loop paragraph")
s = sub1(s, "lowers legitimate action rate round over round, while unauthorized action rate barely moves.}", "lowers the legitimate action rate round over round, while the unauthorized action rate barely moves.}", "loop caption")
# writer compute (black, restored): grammar after rename
s = sub1(s, "unauthorized action rate falls from 13.2\\% to 8.6\\% and legitimate action rate rises from 94.2\\% to 95.8\\%.", "the unauthorized action rate falls from 13.2\\% to 8.6\\% and the legitimate action rate rises from 94.2\\% to 95.8\\%.", "ttc 1")
s = sub1(s, "which also improves downstream behavior to 7.6\\% unauthorized action rate and 97.2\\% legitimate action rate.", "which also improves downstream behavior to a 7.6\\% unauthorized action rate and a 97.2\\% legitimate action rate.", "ttc 2")
# mitigations
s = sub1(s, "source-authority gating cuts unauthorized action rate from 25.3\\% to 7.3\\%", "source-authority gating cuts the unauthorized action rate from 25.3\\% to 7.3\\%", "mit 1")
s = sub1(s, "Both pay in legitimate use: legitimate action rate falls from 93.3\\% to 53.8\\%", "Both pay in legitimate use: the legitimate action rate falls from 93.3\\% to 53.8\\%", "mit 2")
s = sub1(s, "At the representation level, formation falls from 24.9\\% to 5.5\\% and 8.7\\% respectively.", "At the representation level, the false-authority rate falls from 24.9\\% to 5.5\\% and 8.7\\% respectively.", "mit 3")
s = sub1(s, "Source-authority gating also bounds how much origin explains. A false-authority rate of 5.5\\% survives source filtering",
         "Source-authority gating also bounds how much the origin of a record explains. A false-authority rate of 5.5\\% survives source filtering", "mit 4")
s = sub1(s, "mitigation quality must be read jointly from unauthorized action rate and legitimate action rate rather than from safety alone.", "mitigation quality must be read jointly from the unauthorized and legitimate action rates rather than from safety alone.", "mit 5")
s = sub1(s, "and it lowers unauthorized action rate in every domain with no loss of legitimate action rate (Section", "and it lowers the unauthorized action rate in every domain with no loss of legitimate actions (Section", "mit 6")
s = sub1(s, "with legitimate action rate unchanged or higher and the same direction at every seed. Pooled over domains, it is the one point on the frontier of Figure~\\ref{fig:mitigation-pareto} that keeps legitimate action rate within five points of the baseline. The same sentence doubles unauthorized action rate in cybersecurity",
         "with the legitimate action rate unchanged or higher and the same direction at every seed. Pooled over domains, it is the one point on the frontier of Figure~\\ref{fig:mitigation-pareto} that keeps the legitimate action rate within five points of the baseline. The same sentence doubles the unauthorized action rate in cybersecurity", "mit 7")
s = sub1(s, "These runs leave open why the instruction degrades the writer's output. What they establish is that a rule about authority must match the error the writer makes, and that this error can be read from the saved memories before the executor is granted tools (Appendix~\\ref{app:diagnosis}).}",
         "These runs leave open why the instruction degrades the writer's output, but they establish that a rule about authority must match the error the writer makes and that this error can be read from the saved memories before the executor is granted tools (Appendix~\\ref{app:diagnosis}).}", "mit 8")
# limitations, conclusion
s = sub1(s, "the pressure intervention, whose effect on legitimate action rate also concentrates in one executor", "the pressure intervention, whose effect on the legitimate action rate also concentrates in one executor", "lim 1")
s = sub1(s, "\\revised{The writer's error has a location and a shape. On matched histories, false authority forms only after", "\\revised{The writer's error has a location and a shape: on matched histories, false authority forms only after", "concl 1")
s = sub1(s, "and preserves the legitimate action rate that the origin filters sacrifice.", "and preserves the legitimate actions that the origin filters sacrifice.", "concl 2")
s = sub1(s, "point toward memory architectures that preserve origin and authorization lifecycles", "point toward memory architectures that preserve the origin and lifecycle of each permission", "concl 3")
s = sub1(s, "Stored permissions deserve the same origin, lifecycle, and audit discipline as entries", "Stored permissions deserve the same origin, lifecycle, and audit discipline as entries", "concl 4")
# related work: the cited paper's own term
s = sub1(s, "formalizes source-authority non-amplification using platform-maintained origin, starting from", "formalizes source-authority non-amplification using platform-maintained origin records, starting from", "related 1")
s = sub1(s, "from those that preserve authoritative origin but corrupt scope", "from those that preserve an authoritative origin but corrupt scope", "related 2")
# table captions: define the abbreviations
s = sub1(s, "\\caption{\\textbf{Legitimate action rate (LA, higher is better) and unauthorized\n  submission (UA, lower is better) by writer and domain",
         "\\caption{\\textbf{Legitimate action rate (LA, higher is better) and unauthorized\n  action rate (UA, lower is better) by writer and domain", "writer table caption")
s = sub1(s, "Positive values indicate higher authorized\n  use, fewer unauthorized actions, or higher paired",
         "Positive values indicate a higher legitimate action\n  rate, fewer unauthorized actions, or higher paired", "cue caption")
s = sub1(s, "Values report legitimate action rate (A) and\n  unauthorized action rate (U), in percentage points.}", "Values report the legitimate action rate (A) and\n  the unauthorized action rate (U), in percentage points.}", "decomposition caption")
s = sub1(s, "the capacity test, the memory designs, and the origin mitigations on Inkling", "the capacity test, the memory designs, and the origin-based mitigations on Inkling", "appendix intro")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ appendix files: headings and short sentences
p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "\\subsection{\\added{Origin mitigations on the added writers}}", "\\subsection{\\added{Origin-based mitigations on the added writers}}", "app heading")
s = sub1(s, "Rebuilding lowers unauthorized action rate for every writer in every domain and raises legitimate action rate (Table~\\ref{tab:writer-side-mitigations}). It is the one design change that holds across writers.",
         "Rebuilding lowers the unauthorized action rate for every writer in every domain and raises the legitimate action rate (Table~\\ref{tab:writer-side-mitigations}), and it is the one design change that holds across writers.", "rebuild sentence")
s = sub1(s, "\\added{When a rebuild lands matters. In the paper's procurement cases", "\\added{When a rebuild lands matters, because in the paper's procurement cases", "rebuild timing")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "\\added{In the paper the executor's actions vanish. In a deployment they are logged, and the log becomes part of the history the writer reads. The closed loop tests what the writer does with those lines.",
         "\\added{In the paper the executor's actions vanish, whereas in a deployment they are logged and the log becomes part of the history the writer reads, so the closed loop tests what the writer does with those lines.", "loop intro")
s = sub1(s, "Second, real grants disappear. In the cybersecurity action arm", "Second, real grants disappear: in the cybersecurity action arm", "grants disappear")
s = sub1(s, "the first closed round matches the open loop within a point (procurement, GPT-OSS-120B, GLM 5.2, Kimi K2.6, Nemotron 3 Ultra). Nothing compounds within one pass.",
         "the first closed round matches the open loop within a point (procurement, GPT-OSS-120B, GLM 5.2, Kimi K2.6, Nemotron 3 Ultra), so nothing compounds within one pass.", "one pass")
s = sub1(s, "In the closed loop every permission record whose only cited sources are the agent's own written-back lines is added, with the write-back block that created it. This stage needs no model.",
         "In the closed loop every permission record whose only cited sources are the agent's own written-back lines is added, with the write-back block that created it, and this stage needs no model.", "no model")
s = sub1(s, "Cybersecurity differs in kind: most of its failures", "Cybersecurity differs in kind, because most of its failures", "differs in kind")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "transfer_pressure_appendix.tex"; s = p.read_text(encoding="utf-8")
s = s.replace("into action it would not otherwise trigger", "into action it would not otherwise take")
p.write_text(s, encoding="utf-8", newline="\n")
print("rename applied")
