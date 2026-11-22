# Stage microbenchmark (Analyst, v4 insights)

This counts the instructions each step of event parsing costs on real seed-42 lines, single-threaded. It isn't exact
end to end, and nothing here is shipped.

`src/scan.rs` and `src/dec.rs` are verbatim copies of the functions from `method/v3` `29b64bf` (`v3::`) and
`method/v4` `c9e1a0c` (`v4::`, `dec::`), made public. They have the same bodies as the engine's.

    cargo build --release
    head -c 200000000 data/seed-42/events/<largest>.csv | sed '$d' > ev200.csv
    /usr/bin/time -l target/release/scanbench ev200.csv MODE   # read "instructions retired"

Subtract mode 0 (load only), then divide by the record count printed on stderr.

| Mode | What it runs |
| --- | --- |
| 0 | load only |
| 1 | memchr line iteration only |
| 2 | memchr + v1 `split_fields` on every line |
| 3 | v3 `for_each_record` (NEON) |
| 4 | v4 `for_each_record` (NEON) |
| 5 / 6 | v3 / v4 with SWAR |
| 7 | 4 + `pack` of `event_id` and `user_id` |
| 8 | 7 + `TimestampDecoder::parse` of `ts` and `ingest_ts` |
| 9 | 8 + type match and `parse_price` |
| 10 | 9 + product category through `IdIndex` (50k direct products) |
