# Fuzz mutation self-test

37/37 mutants killed; fixtures alone kill 24, fuzz (252 strict cases) kills 37. Controls survive (OK).

| Mutant | Fixtures | Fuzz | First killing seeds |
| --- | --- | --- | --- |
| gap >= 30 min splits | kill | kill | [0, 1, 2, 3, 4] |
| late cutoff >= 24 h | kill | kill | [4, 17, 27, 29, 32] |
| click exactly 7 d before excluded | kill | kill | [1, 2, 3, 4, 9] |
| click at session start excluded | kill | kill | [1, 3, 4, 9, 10] |
| tie click -> largest click_id | kill | kill | [1, 2, 3, 4, 5] |
| dedup keeps latest ingest | kill | kill | [0, 1, 2, 3, 4] |
| dedup after validation | kill | kill | [0, 1, 4, 5, 9] |
| F3 wraps at 2^64 | — | kill | [1, 4, 9, 10, 14] |
| F3 wraps at 2^63 | — | kill | [1, 4, 9, 10, 14] |
| F3 longer than 19 chars rejected | — | kill | [0, 1, 2, 3, 4] |
| offset hour 24 accepted | — | kill | [1, 2, 4, 9, 10] |
| offset minute 60 accepted | kill | kill | [1, 4, 11, 12, 13] |
| offset sign inverted | kill | kill | [0, 1, 2, 3, 4] |
| lowercase z accepted | — | kill | [1, 5, 11, 21, 39] |
| hour 24 accepted | — | kill | [1, 5, 9, 10, 11] |
| second 60 accepted | — | kill | [1, 10, 15, 17, 27] |
| no leap years | — | kill | [2, 11, 27, 28, 37] |
| price wraps at 2^32 | — | kill | [4, 9, 17, 24, 27] |
| price 0 accepted | — | kill | [0, 2, 4, 5, 9] |
| price max exclusive | — | kill | [1, 2, 4, 5, 9] |
| \r treated as line ending | kill | kill | [0, 1, 2, 4, 5] |
| inner quotes tolerated | — | kill | [0, 1, 2, 4, 5] |
| half-quoted field tolerated | kill | kill | [0, 1, 2, 4, 5] |
| person named by largest ID | kill | kill | [0, 1, 2, 3, 4] |
| user IDs case-folded | kill | kill | [1, 2, 4, 5, 9] |
| user IDs trimmed | kill | kill | [1, 2, 4, 5, 9] |
| links ignored | kill | kill | [0, 1, 2, 3, 4] |
| only direct links (no transitivity) | kill | kill | [0, 1, 2, 3, 4] |
| top category tie -> largest | kill | kill | [2, 4, 5, 9, 14] |
| assists counted per click | kill | kill | [0, 1, 2, 3, 4] |
| event window end inclusive | kill | kill | [0, 1, 2, 4, 9] |
| click window start exclusive | kill | kill | [146, 147] |
| day = last event's date | kill | kill | [1, 2, 3, 4, 5] |
| header line parsed as data | — | kill | [0, 1, 2, 4, 5] |
| unknown product -> empty category | kill | kill | [2, 4, 9, 10, 15] |
| view/cart need a valid price | kill | kill | [0, 1, 2, 3, 4] |
| unknown campaign clicks kept | kill | kill | [1, 2, 4, 5, 9] |
| CONTROL dedup ties keep last copy | — | — | [] |
| CONTROL clicks keep last copy | — | — | [] |
