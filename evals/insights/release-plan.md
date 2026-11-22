# Release plan to 11:00 ET (Sunday)

Analyst, 00:15 ET. One full eval is about 16 min, plus the amd64 stage, so **plan 35 min from commit to verdict**. Practice submissions are capped at 2 per hour. The feature freeze is at 08:00. After 08:00, only fixes to a train that already exists go in.

## Trains (revised 01:00 ET, after the 21:08 generator change and the gVisor reproduction)

**The gate is now three things:** Eval on the **new** data, fixtures, dev, and **the gVisor (runsc) harness time** from Explorer 5. The harness predicts the board: v5 gives 2.23 s in the harness against 2.146 s on the board.

| Train | Contents | Method commits by | Verdict (Eval + gVisor) | User submits | If a gate fails |
| --- | --- | --- | --- | --- | --- |
| v5 `5b7bcc2` | submitted: **2.146 s** | — | — | done | — |
| **v7** | v5 + **exact lock-free u128 path for 33-byte IDs** + click sort + sessions moves that are gated. **Writer held back** (v4 Parquet settings). | **02:30**. If click sort or sessions isn't gated by then, ship the long-ID fix without it. | 03:05 | **≈ 03:15** | Fall back to v5 + long-ID fix alone. If that fails too, stay on v5. |
| v7 repeat | the same binary | — | — | ≈ 03:45 | Measures board noise at the new level. |
| **v8** | v7 + gVisor-harness wins (each ≥ 0.05 s in the harness: mimalloc purge off, `pread` input, fewer anon faults) + the per-column decoder if it passes its 06:00 go/no-go + the writer only if the harness shows no regression | **07:00** | 07:35, with 60M under gVisor | ≈ 07:45 | v7 stays the candidate. |
| **Final** | the chosen train, unchanged | **08:00 freeze** | 08:00–09:15: full eval and **gVisor 60M** against the runner-up | the final pick by **10:30** | the runner-up, then v5. |

Spare slots: re-submit the current best only when its board is more than 10% off its gVisor prediction.

## What each submission confirms (20M board)

**Superseded (01:00):** the board is predicted by the gVisor harness time, not by instructions (`board-fit.md` §4). The old formula was Eval's instructions per row × 21.508M ÷ 28.77 G/s. Record each result as a rate: `rate = instr/row × 21.508M ÷ board s`.

| Submission | Confirms |
| --- | --- |
| v4 (being submitted) | The second rate point. Instructions predict 1.17–1.21 s; wall ×3.10 predicts 1.42 s. The gap between those two answers whether board time tracks instructions or cycles. |
| v5, then the v5 repeat | The rate stays within ±5% as emit/timestamp instructions fall. **The repeat gives board noise.** That noise sets the tie band in the pick rule. |
| v6 | The writer moves bytes, not just instructions (88 MB vs 21 MB of Parquet at 20M). A board above prediction means output I/O shows on the scorer. If so, revert the writer settings in the final train. |
| v7, v8 | The parse cuts on x86 (SSE quote mask, SSSE3 decoder). This is the one place the instructions were counted on arm64 and run on a different ISA. A rate drop of more than 5% means the x86 code is worse than its NEON count. |

**After 3 or more points, fit `board = a + b × instr/row`.** If `a` (fixed time: startup, page cache, exit) is more than 0.05 s, the 60M final does not triple it. The final predictions below then use `a + 2.983 × b × instr/row`. If the rate itself is falling, the instruction model is overstating the gains and the board wins (rule 2).

## Final pick rule

1. **Only SUBMIT-READY trains**: every Gate A pass, fixtures 36/36 including amd64, and a 60M Linux run that completes under the memory cap. Correctness beats every timing argument.
2. **Level from the board, growth from the gVisor 60M run.** For each candidate, `final ≈ board20 × g`. Here `g` = **gVisor** 60M wall ÷ 20M wall on the new data, from the same harness session. A train without a board point uses its gVisor 20M time as its level. Trust the board, measured on the real box, for the level. Trust the local 60M/20M ratio for how that candidate scales: dedup and sessions are where the trains differ in cache behaviour. The pure instruction model is only a tiebreaker. Use it alone only for a train with no board point.
3. **When they disagree:** if the board ranks A over B but `g` reverses it, the larger effect wins. Board differences inside **2× the measured board noise** count as a tie, and `g` decides. A `g` difference under 3% is also a tie.
4. **On a tie, pick the train with fewer new moves**: the earlier one, which has had more fuzz time. Ties on the final also go to the earlier submission.
5. If the best train has **only one board reading**, and it beats the runner-up by less than 2× the noise, re-submit it once before 10:30.

Standby: send each Eval result. I'll return the rate, the prediction error, and whether it changes the pick.
