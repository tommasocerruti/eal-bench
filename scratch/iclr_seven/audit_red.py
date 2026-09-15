"""List every changed line in the paper (vs Overleaf head 88d923d) that is not inside \\added{} and is not a bare table cell."""
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ICLR = r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr"
files = ["main.tex", "multiseed_appendix.tex", "memory_design_appendix.tex", "transfer_pressure_appendix.tex", "extension_results_appendix.tex", "extension_mitigations_appendix.tex"]
structural = re.compile(r"^\s*(\\(begin|end|centering|label|midrule|toprule|bottomrule|cmidrule|addlinespace|small|footnotesize|scriptsize|setlength|renewcommand|includegraphics|multirow|input|hfill|par|vspace|shortstack|mdwriter|modelname)|&|\{\\mdcell|\\rowcolor|%|\\textit\{Average\}|(Procurement|Cybersecurity|Finance|procurement|cybersecurity|finance|[0-9]) *&|\\shortstack)")
for f in files:
    out = subprocess.run(["git", "-C", ICLR, "diff", "-U0", "88d923d", "HEAD", "--", f], capture_output=True, text=True, encoding="utf-8").stdout
    print(f"===== {f}")
    for line in out.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        if not body.strip() or structural.match(body):
            continue
        # strip every \added{...} span (balanced) and see what text remains outside red
        s = body
        while True:
            i = s.find("\\added{")
            if i < 0:
                break
            j = i + 7; depth = 1
            while depth and j < len(s):
                depth += (s[j] == "{") - (s[j] == "}"); j += 1
            s = s[:i] + "<RED>" + s[j:]
        outside = re.sub(r"<RED>", "", s).strip()
        if outside and not re.fullmatch(r"[\\a-zA-Z{}\[\]=.,;:()~\s\-]*(caption|textbf|item|section|subsection)?[\\a-zA-Z{}\[\]=.,;:()~\s\-]*", outside) or True:
            # print the non-red remainder if it has letters beyond markup
            if re.search(r"[A-Za-z]{3,}", re.sub(r"\\[a-zA-Z]+|\{|\}", " ", outside)):
                print("  ", outside[:260])
