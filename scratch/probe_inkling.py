"""Latency probe for the Inkling endpoint before starting a writer run. Makes three short sequential calls (a small
structured-reasoning task, 512 output tokens) and prints their latencies; exit 0 when the median is under the threshold
(default 45 s, a fifth of the canonical 180 s writer call limit), 1 otherwise. Usage: python scratch/probe_inkling.py [threshold_s]"""
import statistics
import sys
import time

from eal_bench.llm import LLM

threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
llm = LLM()
prompt = ("Three permissions: A (until 2026-10-01, cap 5000), B (until 2026-09-20, cap 2000), C (revoked 2026-09-10). "
          "Today is 2026-09-25. Which permissions are active, and what is the total cap? Answer in one line.")
lat = []
for i in range(3):
    t = time.time()
    try:
        llm.complete("writer", [{"role": "user", "content": prompt}], target="inkling_baseten", max_tokens=512)
        lat.append(time.time() - t)
        print(f"probe {i + 1}: {lat[-1]:.1f} s")
    except Exception as exc:  # noqa: BLE001
        lat.append(999.0)
        print(f"probe {i + 1}: error {type(exc).__name__}: {str(exc)[:120]}")
med = statistics.median(lat)
print(f"median {med:.1f} s; threshold {threshold:g} s; {'OK' if med < threshold else 'SLOW'}")
sys.exit(0 if med < threshold else 1)
