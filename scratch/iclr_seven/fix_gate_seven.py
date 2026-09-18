"""Seven-writer representation-level gate table (primary seed) and the surviving false-authority rate in Section 4.6."""
import json
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
T = json.load(open("scratch/iclr_seven/gate_added_table.json", encoding="utf-8"))
G = json.load(open("scratch/iclr_seven/gate_added.json", encoding="utf-8"))


def sub1(name, old, new):
    p = ICLR / name
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (name, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("ok", name, old[:50])


def row(label, c, bold=False):
    pct = lambda k, n: f"{100 * k / n:.1f}" + B + "%"
    red = f"{100 * (1 - c['F_after'] / c['F_before']):.1f}" + B + "%" if c["F_before"] else "0.0" + B + "%"
    cells = [f"{c['F_before']}/{c['unauth']} ({pct(c['F_before'], c['unauth'])})", f"{c['F_after']}/{c['unauth']} ({pct(c['F_after'], c['unauth'])})",
             red, f"{c['valid_after']}/{c['auth']} ({pct(c['valid_after'], c['auth'])})"]
    if bold:
        cells = [B + "textbf{" + x + "}" for x in cells]
        label = B + "textbf{" + label + "}"
    return "    " + label + " & " + " & ".join(cells) + " " + B + B


old_rows = ("    Procurement & 58/360 (16.1" + B + "%) & 2/360 (0.6" + B + "%) & 96.6" + B + "% & 177/360 (49.2" + B + "%) " + B + B + "\n"
            "    Cybersecurity & 28/640 (4.4" + B + "%) & 28/640 (4.4" + B + "%) & 0.0" + B + "% & 606/640 (94.7" + B + "%) " + B + B + "\n"
            "    Finance & 80/320 (25.0" + B + "%) & 0/320 (0.0" + B + "%) & 100.0" + B + "% & 204/320 (63.8" + B + "%) " + B + B + "\n"
            "    " + B + "midrule\n"
            "    " + B + "textbf{All} & " + B + "textbf{166/1320 (12.6" + B + "%)} & " + B + "textbf{30/1320 (2.3" + B + "%)} & " + B + "textbf{81.9" + B + "%} & " + B + "textbf{987/1320 (74.8" + B + "%)} " + B + B)
new_rows = "\n".join([row("Procurement", T["procurement"]), row("Cybersecurity", T["cybersecurity"]), row("Finance", T["finance"]), "    " + B + "midrule", row("All", T["all"], bold=True)])
sub1("source_authority_appendix.tex", old_rows, new_rows)

# Section 4.6: surviving false-authority rate, seven writers, three seeds
five_after, five_n = 108, 1980
add_after = sum(v["F_after"] for v in G.values()); add_n = sum(v["unauth"] for v in G.values())
rate = 100 * (five_after + add_after) / (five_n + add_n)
print(f"surviving false authority: {five_after + add_after}/{five_n + add_n} = {rate:.1f}%")
sub1("main.tex", "A false-authority rate of 5.5" + B + "% survives source filtering,",
     "A false-authority rate of " + B + "updated{" + f"{rate:.1f}" + B + "%} survives source filtering,")
print("done")
