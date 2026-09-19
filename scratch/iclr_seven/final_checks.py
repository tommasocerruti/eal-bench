"""Writing-rule scans on the compiled paper: hanging single-word lines, number-initial sentences, banned words,
unbalanced colour macros. Exit code 1 if anything is found outside the verbatim prompt appendix."""
import re
import subprocess
import sys
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
txt = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(ICLR / "main.pdf"), "-"], capture_output=True).stdout.decode("utf-8", "ignore")
lines = txt.splitlines()
problems = []
for i, l in enumerate(lines[:-1]):
    t = re.sub(r"^\s*\d{3,4}\s", "", l).strip()
    if not t:
        continue
    prev = re.sub(r"^\s*\d{3,4}\s", "", lines[i - 1]).strip() if i else ""
    if len(t.split()) == 1 and lines[i + 1].strip() == "" and len(prev) > 70 and re.search(r"[a-z]{3}", t) and not re.search(r"[&|]", prev):
        problems.append(f"hanging word: ...{prev[-30:]} -> {t}")
text = " ".join(re.sub(r"^\s*\d{3,4}\s", "", l).strip() for l in lines)
for m in re.finditer(r"(?:[.!?]|^)\s+((?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Twelve)\b[^.]{0,50})", text):
    if "active mandate" not in m.group(1) and "presented as control" not in m.group(1):  # verbatim finance prompt; co-author caption
        problems.append("number-initial: " + m.group(1))
for w in re.findall(r"\b(honest\w*|trigger\w*|provenance)\b", text, flags=re.I):
    if w.lower() not in ("triggers", "provenance"):  # verbatim prompt and the PPMF paper title
        problems.append("banned word: " + w)
B = chr(92)
for name in ICLR.glob("*.tex"):
    t = name.read_text(encoding="utf-8")
    for m in re.finditer(B + B + "(revised|updated|added)" + B + "{", t):
        k = m.end(); depth = 1
        while k < len(t) and depth:
            if t[k] == B:
                k += 2; continue
            depth += (t[k] == "{") - (t[k] == "}"); k += 1
        if depth:
            problems.append(f"unclosed {m.group(1)} in {name.name} at line {t[:m.start()].count(chr(10)) + 1}")
log = (ICLR / "main.log").read_text(encoding="utf-8", errors="ignore")
for key in ("undefined", "multiply"):
    if key in log:
        problems.append(f"latex log mentions '{key}'")
pages = subprocess.run(["pdfinfo", str(ICLR / "main.pdf")], capture_output=True, text=True).stdout
print(pages.strip().split("Pages:")[1].split(chr(10))[0].strip(), "pages")
refs = subprocess.run(["pdftotext", "-enc", "UTF-8", "-f", "10", "-l", "11", "-layout", str(ICLR / "main.pdf"), "-"], capture_output=True).stdout.decode("utf-8", "ignore")
print("REFERENCES on page 10 or 11:", "REFERENCES" in refs)
for p in problems:
    print("PROBLEM", p)
print("problems:", len(problems))
sys.exit(1 if problems else 0)
