# Fuzz mutation self-test

37/37 mutants killed; fixtures alone kill 24, fuzz (254 strict cases) kills 37. Controls survive (OK).

| Mutant | Fixtures | Fuzz | First killing seeds |
| --- | --- | --- | --- |
| gap >= 30 min splits | kill | kill | [0, 1, 2, 3, 4] |
| late cutoff >= 24 h | kill | kill | [20, 24, 27, 41, 53] |
| click exactly 7 d before excluded | kill | kill | [2, 3, 13, 14, 15] |
| click at session start excluded | kill | kill | [2, 3, 11, 12, 13] |
| tie click -> largest click_id | kill | kill | [2, 3, 5, 9, 11] |
| dedup keeps latest ingest | kill | kill | [0, 1, 2, 3, 4] |
| dedup after validation | kill | kill | [0, 2, 3, 5, 9] |
| F3 wraps at 2^64 | — | kill | [2, 3, 14, 17, 23] |
| F3 wraps at 2^63 | — | kill | [2, 3, 13, 14, 17] |
| F3 longer than 19 chars rejected | — | kill | [0, 1, 2, 3, 4] |
| offset hour 24 accepted | — | kill | [3, 11, 14, 17, 21] |
| offset minute 60 accepted | kill | kill | [11, 25, 29, 31, 41] |
| offset sign inverted | kill | kill | [0, 2, 3, 5, 9] |
| lowercase z accepted | — | kill | [2, 4, 5, 9, 11] |
| hour 24 accepted | — | kill | [5, 11, 20, 31, 41] |
| second 60 accepted | — | kill | [11, 15, 17, 25, 41] |
| no leap years | — | kill | [28] |
| price wraps at 2^32 | — | kill | [17, 24, 27, 31, 47] |
| price 0 accepted | — | kill | [0, 2, 3, 4, 5] |
| price max exclusive | — | kill | [2, 3, 4, 5, 9] |
| \r treated as line ending | kill | kill | [0, 1, 2, 3, 4] |
| inner quotes tolerated | — | kill | [0, 2, 3, 4, 5] |
| half-quoted field tolerated | kill | kill | [0, 2, 3, 4, 5] |
| person named by largest ID | kill | kill | [0, 1, 2, 3, 4] |
| user IDs case-folded | kill | kill | [2, 3, 4, 5, 9] |
| user IDs trimmed | kill | kill | [2, 3, 4, 5, 9] |
| links ignored | kill | kill | [0, 1, 2, 3, 4] |
| only direct links (no transitivity) | kill | kill | [0, 1, 2, 3, 4] |
| top category tie -> largest | kill | kill | [49] |
| assists counted per click | kill | kill | [0, 2, 3, 4, 5] |
| event window end inclusive | kill | kill | [0, 2, 3, 4, 9] |
| click window start exclusive | kill | kill | [34, 49, 51] |
| day = last event's date | kill | kill | [1, 2, 3, 4, 5] |
| header line parsed as data | — | kill | [0, 1, 2, 4, 5] |
| unknown product -> empty category | kill | kill | [2, 14, 15, 20, 24] |
| view/cart need a valid price | kill | kill | [0, 1, 2, 3, 4] |
| unknown campaign clicks kept | kill | kill | [2, 3, 4, 5, 9] |
| CONTROL dedup ties keep last copy | — | — | [] |
| CONTROL clicks keep last copy | — | — | [] |
