dataset data/dev: events 1,071,894 clicks 255,147 links 44,906 lines

| phase | 5b7bcc2 ARM | 5b7bcc2 x86 raw | 5b7bcc2 x86 corr | x86/ARM | e693e18 ARM | e693e18 x86 raw | e693e18 x86 corr | x86/ARM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lookups | 119 | 55 | 52 | 0.43 | 121 | 54 | 51 | 0.42 |
| events | 829 | 816 | 813 | 0.98 | 768 | 804 | 804 | 1.05 |
| clicks | 171 | 163 | 162 | 0.95 | 148 | 150 | 150 | 1.01 |
| dedup | 39 | 107 | 49 | 1.23 | 40 | 106 | 49 | 1.20 |
| sessions | 302 | 356 | 333 | 1.10 | 244 | 277 | 253 | 1.04 |
| write | 181 | 184 | 171 | 0.95 | 179 | 186 | 174 | 0.97 |
| **total** | 1,642 | 1,680 | 1,579 | 0.96 | 1,501 | 1,577 | 1,480 | 0.99 |

(all per event line; own-line rates: events/event line, clicks/click line)

5b7bcc2: events/event-line x86 813 (ARM 829); clicks/click-line x86 681 (ARM 720)
   lookups: Ids::intern 11,111 calls, 4,562,857 Ir incl = 411/call, 4.3 per event line; of which HashMap entry 8,343,273, rehash 1,509,834
   events: Ids::intern 260,402 calls, 95,408,937 Ir incl = 366/call, 89.0 per event line; of which HashMap entry 57,496,844, rehash 23,742,791
   clicks: Ids::intern 62,428 calls, 16,576,719 Ir incl = 266/call, 15.5 per event line; of which HashMap entry 7,985,584, rehash 0
   lookups: Ids::bytes 1,177,518 Ir incl (19,924 calls from user_batch)
   sessions: Ids::bytes 205,160 Ir incl (3,740 calls from user_batch)
   write: Ids::bytes 8,014,524 Ir incl (118,107 calls from user_batch)
   rep-string bytes counted as Ir: lookups 3.3M, events 3.6M, clicks 0.7M, dedup 64.3M, sessions 25.6M, write 13.9M
e693e18: events/event-line x86 804 (ARM 768); clicks/click-line x86 628 (ARM 621)
   lookups: Ids::intern 7 calls, 3,423 Ir incl = 489/call, 0.0 per event line; of which HashMap entry 5,472,145, rehash 906
   events: Ids::intern 3 calls, 1,581 Ir incl = 527/call, 0.0 per event line; of which HashMap entry 798, rehash 453
   lookups: Ids::bytes 2,400,383 Ir incl (18,562 calls from user_batch)
   sessions: Ids::bytes 255,929 Ir incl (1,978 calls from user_batch)
   write: Ids::bytes 10,547,668 Ir incl (118,107 calls from user_batch)
   rep-string bytes counted as Ir: lookups 3.3M, events 0.3M, clicks 0.4M, dedup 64.0M, sessions 25.8M, write 13.8M
