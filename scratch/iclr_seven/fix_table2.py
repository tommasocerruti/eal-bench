"""Table 2 (tab:writer-domain): unauthorized action rate columns before legitimate action rate in every block,
rows sorted by average baseline unauthorized action rate (lowest first), Average row last."""
import pathlib
import re

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
p = ICLR / "main.tex"
t = p.read_text(encoding="utf-8")
lab = t.index(B + "label{tab:writer-domain}")
start = t.rfind(B + "begin{table}", 0, lab)
end = t.index(B + "end{table}", lab) + len(B + "end{table}")
tab = t[start:end]

# caption: name UA first
old_cap = (B + "caption{" + B + "textbf{Legitimate action rate (LA, higher is better) and unauthorized\n  action rate (UA, lower is better) by writer and domain, at baseline (B) and\n  under pressure (P).}")
assert tab.count(old_cap) == 1, "caption"
tab = tab.replace(old_cap, B + "caption{" + B + "textbf{Unauthorized action rate (UA, lower is better) and legitimate\n  action rate (LA, higher is better) by writer and domain, at baseline (B) and\n  under pressure (P).}")
# header: swap the two-column group labels
la = B + "multicolumn{2}{c}{LA $" + B + "uparrow$}"; ua = B + "multicolumn{2}{c}{UA $" + B + "downarrow$}"
assert tab.count(la + " & " + ua) == 4, tab.count(la + " & " + ua)
tab = tab.replace(la + " & " + ua, ua + " & " + la)

# body rows
i = tab.index(B + "midrule") + len(B + "midrule") + 1
j = tab.index("    " + B + "bottomrule")
body = tab[i:j]
rows = re.split(r"(?<=" + B + B + B + B + r")\n", body.strip("\n"))
rows = [r for r in rows if r.strip()]
assert len(rows) == 8, len(rows)


def reorder(row):
    lines = row.split("\n")
    head, blocks = lines[0], lines[1:]
    assert len(blocks) == 4, blocks
    out = [head]
    for b in blocks:
        cells = [c.strip() for c in b.strip().lstrip("&").rstrip(B + B).split(" & ")]
        assert len(cells) == 4, cells
        new = [cells[2], cells[3], cells[0], cells[1]]
        tail = " " + B + B if b.rstrip().endswith(B + B) else ""
        out.append("      & " + " & ".join(new) + tail)
    return "\n".join(out)


def avg_ua_b(row):
    last = row.split("\n")[4]
    cells = [c.strip() for c in last.strip().lstrip("&").rstrip(B + B).split(" & ")]
    val = lambda c: float(re.search(r"(\d+\.\d)", c).group(1))
    return (val(cells[2]), val(cells[3]))


writers, average = rows[:-1], rows[-1]
assert average.lstrip().startswith(B + "textit{Average}"), average[:40]
writers.sort(key=avg_ua_b)
print("order:", [re.search(r"\}\{([^}]+)\}", w.split(chr(10))[0]).group(1) for w in writers])
new_body = "\n".join(reorder(r) for r in writers + [average]) + "\n"
tab = tab[:i] + new_body + tab[j:]
t = t[:start] + tab + t[end:]
p.write_text(t, encoding="utf-8", newline="\n")
print("table 2 rewritten")
