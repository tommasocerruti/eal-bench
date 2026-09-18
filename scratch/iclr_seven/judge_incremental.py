"""Judge the failures of completed parity runs that have not been judged yet, group by group (same judges and labels)."""
import glob, json, os, subprocess, sys
W = ["grok_4_3_openrouter", "qwen_plus_0728_openrouter"]
GROUPS = [("open-seeds", ["results/procurement/*__newwriter-s*-{w}"]), ("memtable-cyber", ["results/cybersecurity/*__memtable-cybersecurity-{w}"]),
          ("memtable-finance", ["results/finance/*__memtable-finance-{w}"]), ("memtable-seeds", ["results/cybersecurity/*__memtable-s*-cybersecurity-{w}", "results/finance/*__memtable-s*-finance-{w}"]),
          ("mandate-open", ["results/*/*__mandate-*{w}"]), ("open-generated-v2", ["results/procurement/*__generated-v2-{w}", "results/procurement/*__mandate-generated-v2-{w}"]),
          ("loop-both", ["results/*/*__rounds3v2-both-*-{w}"])]
ONLY = set(sys.argv[1:])
for group, pats in GROUPS:
    if ONLY and group not in ONLY:
        continue
    todo = []
    for w in W:
        for pat in pats:
            for d in glob.glob(pat.format(w=w)):
                d = d.replace(chr(92), "/")
                if "superseded" in d or "glm53" in d: continue
                try:
                    if json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") != "completed": continue
                except Exception:
                    continue
                tag = d.split("__")[-1]
                if os.path.exists(f"results/diagnosis/v2/{group}/{tag}.jsonl"): continue
                todo.append(d)
    if not todo:
        print(group, "nothing new"); continue
    print(group, "judging", len(todo), "runs", flush=True)
    r = subprocess.run([sys.executable, "-m", "experiments.diagnose_formation", *todo, "--out", f"results/diagnosis/v2/{group}"], capture_output=True, text=True)
    print(group, "ok" if r.returncode == 0 else "FAILED " + r.stderr[-400:], flush=True)
