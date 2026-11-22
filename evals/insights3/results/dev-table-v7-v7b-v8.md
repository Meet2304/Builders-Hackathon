dataset data/dev: events 1,071,894 clicks 255,147 links 44,906 lines

| phase | e693e18 ARM | e693e18 x86 raw | e693e18 x86 corr | x86/ARM | 96af24b ARM | 96af24b x86 raw | 96af24b x86 corr | x86/ARM | 2b9aecd ARM | 2b9aecd x86 raw | 2b9aecd x86 corr | x86/ARM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lookups | 121 | 54 | 51 | 0.42 | 121 | 54 | 51 | 0.42 | 119 | 53 | 50 | 0.42 |
| events | 768 | 804 | 804 | 1.05 | 767 | 804 | 804 | 1.05 | 737 | 753 | 753 | 1.02 |
| clicks | 148 | 150 | 150 | 1.01 | 147 | 150 | 149 | 1.02 | 107 | 107 | 106 | 0.99 |
| dedup | 40 | 106 | 49 | 1.20 | 37 | 106 | 48 | 1.31 | 34 | 106 | 48 | 1.41 |
| sessions | 244 | 277 | 253 | 1.04 | 239 | 277 | 253 | 1.06 | 236 | 277 | 253 | 1.08 |
| write | 179 | 186 | 174 | 0.97 | 178 | 186 | 173 | 0.98 | 178 | 186 | 173 | 0.97 |
| **total** | 1,501 | 1,577 | 1,480 | 0.99 | 1,488 | 1,577 | 1,480 | 0.99 | 1,411 | 1,481 | 1,384 | 0.98 |

(all per event line; own-line rates: events/event line, clicks/click line)

e693e18: events/event-line x86 804 (ARM 768); clicks/click-line x86 628 (ARM 621)
   lookups: Ids::intern 7 calls, 3,423 Ir incl = 489/call, 0.0 per event line; of which HashMap entry 5,472,145, rehash 906
   events: Ids::intern 3 calls, 1,581 Ir incl = 527/call, 0.0 per event line; of which HashMap entry 798, rehash 453
   lookups: Ids::bytes 2,400,383 Ir incl (18,562 calls from user_batch)
   sessions: Ids::bytes 255,929 Ir incl (1,978 calls from user_batch)
   write: Ids::bytes 10,547,668 Ir incl (118,107 calls from user_batch)
   rep-string bytes counted as Ir: lookups 3.3M, events 0.3M, clicks 0.4M, dedup 64.0M, sessions 25.8M, write 13.8M
96af24b: events/event-line x86 804 (ARM 767); clicks/click-line x86 628 (ARM 618)
   lookups: Ids::intern 7 calls, 3,423 Ir incl = 489/call, 0.0 per event line; of which HashMap entry 5,472,145, rehash 906
   events: Ids::intern 3 calls, 1,581 Ir incl = 527/call, 0.0 per event line; of which HashMap entry 798, rehash 453
   lookups: Ids::bytes 2,400,383 Ir incl (18,562 calls from user_batch)
   sessions: Ids::bytes 255,929 Ir incl (1,978 calls from user_batch)
   write: Ids::bytes 10,547,668 Ir incl (118,107 calls from user_batch)
   rep-string bytes counted as Ir: lookups 3.3M, events 0.3M, clicks 0.4M, dedup 64.0M, sessions 25.8M, write 13.8M
2b9aecd: events/event-line x86 753 (ARM 737); clicks/click-line x86 446 (ARM 450)
   lookups: Ids::intern 7 calls, 3,423 Ir incl = 489/call, 0.0 per event line; of which HashMap entry 5,472,145, rehash 906
   events: Ids::intern 3 calls, 1,581 Ir incl = 527/call, 0.0 per event line; of which HashMap entry 798, rehash 453
   lookups: Ids::bytes 2,400,383 Ir incl (18,562 calls from user_batch)
   sessions: Ids::bytes 255,929 Ir incl (1,978 calls from user_batch)
   write: Ids::bytes 10,547,668 Ir incl (118,107 calls from user_batch)
   rep-string bytes counted as Ir: lookups 3.3M, events 0.3M, clicks 0.4M, dedup 64.0M, sessions 25.8M, write 13.8M
