# Eval ledger

One row per eval run (newest last). Details: `results/<version>.json`.

| Date | Version | Commit | Profile | Fixtures n/arm/amd | dev | Diff | Fuzz | Det | 1M | 20M | 60M | Footprint 60M | Verdict | Board 20M (est.) | Linux 20M | Instr/row 20M | Board 20M (instr.) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-21T17:24 | v1 | 3e486624 | full | 36/36/36 | MATCH | 10/10 | 842/842 | yes | 0.132s | 1.550s | 5.793s | 11.5 GB | SUBMIT-READY | 4.809s | n/a | - | n/a |
| 2026-11-21T18:02 | v2 | 953af436 | full | 36/36/36 | MATCH | 11/11 | 854/854 | yes | 0.134s | 1.661s | 5.367s | 11.4 GB | HOLD | 5.155s | n/a | 4,264 | 3.187s |
| 2026-11-21T18:43 | v3 | 29b64bfc | full | 36/36/36 | MATCH | 11/11 | 854/854 | yes | 0.079s | 0.624s (noisy) | 1.970s (noisy) | 5.6 GB | SUBMIT-READY | 1.936s | 0.550s (noisy) | 2,598 | 1.942s |
| 2026-11-21T21:52 | v4 | a0197396 | full | 36/36/36 | MATCH | 11/11 | 854/854 | yes | 0.079s (noisy) | 0.457s (noisy) | 1.320s | 5.1 GB | SUBMIT-READY | 1.418s | 0.383s | 1,572 | 1.175s |
