"""Run gen.py cases through the oracle and a binary under several knobs; exact compare.

Usage: run.py BINARY N_SEEDS WORKDIR
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PY = os.path.join(ROOT, ".venv", "bin", "python")
KNOBS = [
    {},
    {"SESSIONS_DEBUG_HASH_BITS": "0"},  # every long ID collides: probe windows overflow to the interner
    {"SESSIONS_DEBUG_HASH_BITS": "3", "SESSIONS_DEBUG_PARTS": "1"},
    {"SESSIONS_DEBUG_NO_FAST": "1"},
    {"SESSIONS_DEBUG_NO_FAST": "2"},
    {"SESSIONS_DEBUG_NO_FAST": "3", "SESSIONS_DEBUG_CHUNK": "97"},
]


def main():
    binary, n, work = os.path.abspath(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    fails = runs = 0
    for seed in range(1, n + 1):
        d = os.path.join(work, f"s{seed}")
        shutil.rmtree(d, ignore_errors=True)
        inp, exp = os.path.join(d, "in"), os.path.join(d, "exp")
        subprocess.run([PY, os.path.join(HERE, "gen.py"), str(seed), inp], check=True)
        subprocess.run([PY, os.path.join(ROOT, "reference", "reference.py"), inp, exp], check=True, stdout=subprocess.DEVNULL)
        for ki, knob in enumerate(KNOBS):
            got = os.path.join(d, f"got{ki}")
            os.makedirs(got)
            env = {k: v for k, v in os.environ.items() if not k.startswith("SESSIONS_")}
            env.update(knob, DATA_DIR=inp, OUTPUT_DIR=got, SCRATCH_DIR=os.path.join(d, "scr"), NCPU=str([8, 2, 1][seed % 3]))
            p = subprocess.run([binary], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            c = subprocess.run([PY, os.path.join(ROOT, "scripts", "compare.py"), got, exp], capture_output=True, text=True)
            runs += 1
            ok = p.returncode == 0 and c.stdout.strip().endswith("MATCH") and "MISMATCH" not in c.stdout
            if not ok:
                fails += 1
                print(f"FAIL seed={seed} knob={knob} rc={p.returncode}\n{p.stderr.decode()[-400:]}\n{c.stdout[-800:]}", flush=True)
        if fails == 0:
            shutil.rmtree(d, ignore_errors=True)
    print(f"{runs - fails}/{runs} MATCH ({n} seeds x {len(KNOBS)} knobs)")


if __name__ == "__main__":
    main()
