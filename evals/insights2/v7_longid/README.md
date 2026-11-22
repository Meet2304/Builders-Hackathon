# v7 long-ID adversarial suite (Analyst 2)

Inputs that stress byte-wise ID ordering and equality across packed, long (prefix + 32 lowercase hex) and interned keys. Each case is checked against `reference/reference.py` under 6 debug-knob settings, including `SESSIONS_DEBUG_HASH_BITS=0`, which forces long IDs to overflow into the interner.

```sh
.venv/bin/python evals/insights2/v7_longid/run.py <binary> 150 /tmp/v7_longid
```

The last line reads `N/M MATCH`. A failing seed keeps its directory (`in/`, `exp/`, `got<k>/`). On `e693e18` the result is 900/900. Four deliberately broken builds are each caught on 18 to 20 of 20 seeds (see `evals/insights2/verify-v7.md`).
