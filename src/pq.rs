//! Direct Parquet encoder for `user_daily`: the fixed schema goes straight into pages,
//! with no Arrow builders, no statistics and one row group per file.
//!
//! Columns: user_id (dictionary page + RLE_DICTIONARY indices), day (INT32 DATE,
//! dictionary of the file's day range), sessions / events / revenue_cents (INT64,
//! DELTA_BINARY_PACKED), top_category (optional; dictionary of every category name).
//! Every index stream is one bit-packed run of the RLE/bit-packing hybrid.

use crate::UserRow;

// Parquet enums
const T_INT32: i32 = 1;
const T_INT64: i32 = 2;
const T_BYTE_ARRAY: i32 = 6;
const E_PLAIN: i32 = 0;
const E_RLE: i32 = 3;
const E_DELTA: i32 = 5;
const E_RLE_DICT: i32 = 8;
const PAGE_DATA: i32 = 0;
const PAGE_DICT: i32 = 2;
const REQUIRED: i32 = 0;
const OPTIONAL: i32 = 1;
const CONV_UTF8: i32 = 0;
const CONV_DATE: i32 = 6;

// ------------------------------------------------------------ thrift compact protocol

const C_I32: u8 = 5;
const C_I64: u8 = 6;
const C_BINARY: u8 = 8;
const C_LIST: u8 = 9;
const C_STRUCT: u8 = 12;

fn varint(out: &mut Vec<u8>, mut v: u64) {
    while v >= 0x80 {
        out.push(v as u8 | 0x80);
        v >>= 7;
    }
    out.push(v as u8);
}

fn zigzag(v: i64) -> u64 {
    ((v << 1) ^ (v >> 63)) as u64
}

/// One struct being written: field ids must increase.
struct St<'o> {
    out: &'o mut Vec<u8>,
    last: i16,
}

impl<'o> St<'o> {
    fn new(out: &'o mut Vec<u8>) -> Self {
        St { out, last: 0 }
    }
    fn field(&mut self, id: i16, ctype: u8) {
        let d = id - self.last;
        debug_assert!(d > 0 && d <= 15);
        self.out.push((d as u8) << 4 | ctype);
        self.last = id;
    }
    fn i32(&mut self, id: i16, v: i32) -> &mut Self {
        self.field(id, C_I32);
        varint(self.out, zigzag(v as i64));
        self
    }
    fn i64(&mut self, id: i16, v: i64) -> &mut Self {
        self.field(id, C_I64);
        varint(self.out, zigzag(v));
        self
    }
    fn bin(&mut self, id: i16, b: &[u8]) -> &mut Self {
        self.field(id, C_BINARY);
        varint(self.out, b.len() as u64);
        self.out.extend_from_slice(b);
        self
    }
    /// A nested struct field; `f` writes its fields.
    fn st(&mut self, id: i16, f: impl FnOnce(&mut St)) -> &mut Self {
        self.field(id, C_STRUCT);
        let mut s = St::new(self.out);
        f(&mut s);
        s.out.push(0);
        self
    }
    fn list_header(&mut self, id: i16, n: usize, elem: u8) {
        self.field(id, C_LIST);
        if n < 15 {
            self.out.push((n as u8) << 4 | elem);
        } else {
            self.out.push(0xf0 | elem);
            varint(self.out, n as u64);
        }
    }
    fn list_i32(&mut self, id: i16, v: &[i32]) -> &mut Self {
        self.list_header(id, v.len(), C_I32);
        for &x in v {
            varint(self.out, zigzag(x as i64));
        }
        self
    }
    fn list_bin(&mut self, id: i16, v: &[&[u8]]) -> &mut Self {
        self.list_header(id, v.len(), C_BINARY);
        for b in v {
            varint(self.out, b.len() as u64);
            self.out.extend_from_slice(b);
        }
        self
    }
    /// A list of structs; `f(i, s)` writes element i's fields.
    fn list_st(&mut self, id: i16, n: usize, mut f: impl FnMut(usize, &mut St)) -> &mut Self {
        self.list_header(id, n, C_STRUCT);
        for i in 0..n {
            let mut s = St::new(self.out);
            f(i, &mut s);
            s.out.push(0);
        }
        self
    }
}

// ------------------------------------------------------------ value encoders

/// Little-endian bit packing (Parquet's order), up to 64 bits per value.
struct Bits<'o> {
    out: &'o mut Vec<u8>,
    acc: u128,
    n: u32,
}

impl<'o> Bits<'o> {
    fn new(out: &'o mut Vec<u8>) -> Self {
        Bits { out, acc: 0, n: 0 }
    }
    #[inline(always)]
    fn put(&mut self, v: u64, bw: u32) {
        self.acc |= (v as u128) << self.n;
        self.n += bw;
        if self.n >= 64 {
            self.out.extend_from_slice(&(self.acc as u64).to_le_bytes());
            self.acc >>= 64;
            self.n -= 64;
        }
    }
    fn finish(self) {
        let bytes = self.n.div_ceil(8) as usize;
        self.out.extend_from_slice(&(self.acc as u64).to_le_bytes()[..bytes]);
    }
}

fn varint_len(v: u64) -> usize {
    (bit_width(v).max(1) as usize).div_ceil(7)
}

fn bit_width(max: u64) -> u32 {
    64 - max.leading_zeros()
}

/// Packs `count` values (each < 2^bw, bw <= 32) LSB-first into exactly
/// `count * bw / 8` bytes (`count * bw` a multiple of 8). If `vals` yields fewer
/// than `count` values, the rest pack as zeros.
#[inline(always)]
fn pack32(out: &mut Vec<u8>, vals: impl Iterator<Item = u32>, count: usize, bw: u32) {
    debug_assert!(bw <= 32 && (count * bw as usize) % 8 == 0);
    let bytes = count * bw as usize / 8;
    if bytes == 0 {
        return;
    }
    out.reserve(bytes + 8);
    let start = out.len();
    unsafe {
        let base = out.as_mut_ptr().add(start);
        let mut p = base;
        let (mut acc, mut n) = (0u64, 0u32);
        let mut seen = 0usize;
        for v in vals {
            debug_assert!({ seen += 1; seen <= count });
            debug_assert!(bw == 32 || v >> bw == 0);
            acc |= (v as u64) << n;
            n += bw;
            if n >= 32 {
                p.cast::<u32>().write_unaligned((acc as u32).to_le());
                p = p.add(4);
                acc >>= 32;
                n -= 32;
            }
        }
        // the last partial word, then zero padding up to the exact length
        let rem = bytes - p.offset_from(base) as usize;
        std::ptr::write_bytes(p, 0, rem);
        std::ptr::copy_nonoverlapping(acc.to_le_bytes().as_ptr(), p, rem.min(8));
        out.set_len(start + bytes);
    }
}

/// RLE/bit-packing hybrid body (no length prefix, no width byte): one bit-packed run.
fn hybrid(out: &mut Vec<u8>, vals: impl ExactSizeIterator<Item = u32>, bw: u32) {
    let n = vals.len();
    let groups = n.div_ceil(8);
    varint(out, (groups as u64) << 1 | 1);
    pack32(out, vals, groups * 8, bw);
}

/// DELTA_BINARY_PACKED: blocks of 128 values, 4 miniblocks of 32.
fn delta(out: &mut Vec<u8>, vals: &[i64]) {
    const BLOCK: usize = 128;
    const MINI: usize = 32;
    varint(out, BLOCK as u64);
    varint(out, (BLOCK / MINI) as u64);
    varint(out, vals.len() as u64);
    varint(out, zigzag(vals.first().copied().unwrap_or(0)));
    if vals.len() < 2 {
        return;
    }
    let mut deltas = [0i64; BLOCK];
    let mut prev = vals[0];
    for block in vals[1..].chunks(BLOCK) {
        // one pass: deltas, the block's min and each miniblock's max. The width of
        // a miniblock is that of its largest (d - min), which is (max - min): the
        // true differences are in [0, 2^64), so u64 order matches.
        let k = block.len();
        let minis = k.div_ceil(MINI);
        let (mut min, mut maxs) = (i64::MAX, [i64::MIN; 4]);
        for (m, part) in block.chunks(MINI).enumerate() {
            let mut mx = i64::MIN;
            for (d, &v) in deltas[m * MINI..].iter_mut().zip(part) {
                *d = v.wrapping_sub(prev);
                prev = v;
                min = min.min(*d);
                mx = mx.max(*d);
            }
            maxs[m] = mx;
        }
        varint(out, zigzag(min));
        let mut widths = [0u8; 4];
        for m in 0..minis {
            widths[m] = bit_width(maxs[m].wrapping_sub(min) as u64) as u8;
        }
        out.extend_from_slice(&widths);
        // pad the last miniblock: min - min packs as 0
        for d in &mut deltas[k..minis * MINI] {
            *d = min;
        }
        for (m, &w) in widths.iter().enumerate().take(minis) {
            let mini = &deltas[m * MINI..(m + 1) * MINI];
            if w <= 32 {
                pack32(out, mini.iter().map(|d| d.wrapping_sub(min) as u32), MINI, w as u32);
            } else {
                let mut b = Bits::new(out);
                for d in mini {
                    b.put(d.wrapping_sub(min) as u64, w as u32);
                }
                b.finish();
            }
        }
    }
}

// ------------------------------------------------------------ pages and file

struct Chunk {
    start: usize,
    dict_off: Option<usize>,
    data_off: usize,
    encodings: Vec<i32>,
}

fn page_header(out: &mut Vec<u8>, kind: i32, body: usize, num: usize, enc: i32) {
    let mut s = St::new(out);
    s.i32(1, kind).i32(2, body as i32).i32(3, body as i32);
    if kind == PAGE_DATA {
        s.st(5, |p| {
            p.i32(1, num as i32).i32(2, enc).i32(3, E_RLE).i32(4, E_RLE);
        });
    } else {
        s.st(7, |p| {
            p.i32(1, num as i32).i32(2, E_PLAIN);
        });
    }
    s.out.push(0);
}

fn page(out: &mut Vec<u8>, kind: i32, num: usize, enc: i32, body: &[u8]) {
    assert!(body.len() < i32::MAX as usize, "Parquet page over 2 GiB");
    page_header(out, kind, body.len(), num, enc);
    out.extend_from_slice(body);
}

/// Output column description for the footer.
struct Col {
    name: &'static [u8],
    ty: i32,
    rep: i32,
    conv: Option<i32>,
    logical: i16, // LogicalType union member: 1 STRING, 6 DATE, 0 none
}

const fn col(name: &'static [u8], ty: i32, rep: i32, conv: Option<i32>, logical: i16) -> Col {
    Col { name, ty, rep, conv, logical }
}

const STR: (i32, Option<i32>, i16) = (T_BYTE_ARRAY, Some(CONV_UTF8), 1);
const DATE: (i32, Option<i32>, i16) = (T_INT32, Some(CONV_DATE), 6);
const I64: (i32, Option<i32>, i16) = (T_INT64, None, 0);

/// One single-row-group Parquet file, built column by column in memory.
struct File {
    out: Vec<u8>,
    body: Vec<u8>,
    n: usize,
    chunks: Vec<(Col, Chunk)>,
}

impl File {
    fn new(n: usize, cap: usize) -> Self {
        let mut out = Vec::with_capacity(cap);
        out.extend_from_slice(b"PAR1");
        File { out, body: Vec::with_capacity(cap / 2), n, chunks: Vec::with_capacity(8) }
    }

    /// A dictionary-encoded column: PLAIN dictionary page (`dict`, `n_dict` entries),
    /// then one data page. `defs` (optional columns): definition levels, true = present;
    /// `idx` yields one index per present value.
    fn dict(&mut self, c: Col, dict: &[u8], n_dict: usize, defs: Option<&[bool]>, idx: impl ExactSizeIterator<Item = u32>) {
        let out = &mut self.out;
        let start = out.len();
        page(out, PAGE_DICT, n_dict, E_PLAIN, dict);
        let data_off = out.len();
        // The data page's size is known up front, so its header goes first and the
        // levels and indices pack straight into the file (no body copy).
        let bw = bit_width(n_dict.saturating_sub(1) as u64).max(1);
        let run = |count: usize, bw: u32| {
            let groups = count.div_ceil(8);
            varint_len((groups as u64) << 1 | 1) + groups * bw as usize
        };
        let levels = defs.map(|d| run(d.len(), 1));
        let size = levels.map_or(0, |l| 4 + l) + 1 + run(idx.len(), bw);
        assert!(size < i32::MAX as usize, "Parquet page over 2 GiB");
        page_header(out, PAGE_DATA, size, self.n, E_RLE_DICT);
        let body_at = out.len();
        if let (Some(defs), Some(l)) = (defs, levels) {
            out.extend_from_slice(&(l as u32).to_le_bytes());
            hybrid(out, defs.iter().map(|&d| d as u32), 1);
        }
        out.push(bw as u8);
        hybrid(out, idx, bw);
        debug_assert_eq!(out.len() - body_at, size);
        let encodings = if defs.is_some() { vec![E_PLAIN, E_RLE, E_RLE_DICT] } else { vec![E_PLAIN, E_RLE_DICT] };
        self.chunks.push((c, Chunk { start, dict_off: Some(start), data_off, encodings }));
    }

    /// DATE column: dictionary of every day from the smallest to the largest.
    fn days(&mut self, c: Col, days: impl Iterator<Item = i32> + Clone) {
        let (lo, hi) = days.clone().fold((i32::MAX, i32::MIN), |(lo, hi), d| (lo.min(d), hi.max(d)));
        let mut dict = Vec::with_capacity(4 * (hi - lo + 1) as usize);
        for d in lo..=hi {
            dict.extend_from_slice(&d.to_le_bytes());
        }
        let n = self.n;
        self.dict(c, &dict, (hi - lo) as usize + 1, None, ExactIter { it: days.map(|d| (d - lo) as u32), left: n });
    }

    fn delta(&mut self, c: Col, vals: &[i64]) {
        let start = self.out.len();
        self.body.clear();
        delta(&mut self.body, vals);
        page(&mut self.out, PAGE_DATA, vals.len(), E_DELTA, &self.body);
        self.chunks.push((c, Chunk { start, dict_off: None, data_off: start, encodings: vec![E_DELTA] }));
    }

    fn finish(mut self) -> Vec<u8> {
        let (n, end) = (self.n, self.out.len());
        let chunks = &self.chunks;
        let meta_at = self.out.len();
        {
            let mut fm = St::new(&mut self.out);
            fm.i32(1, 1);
            fm.list_st(2, chunks.len() + 1, |i, s| {
                if i == 0 {
                    s.bin(4, b"schema").i32(5, chunks.len() as i32);
                    return;
                }
                let c = &chunks[i - 1].0;
                s.i32(1, c.ty).i32(3, c.rep).bin(4, c.name);
                if let Some(cv) = c.conv {
                    s.i32(6, cv);
                }
                if c.logical != 0 {
                    // LogicalType union; STRING and DATE are empty structs
                    s.st(10, |u| {
                        u.st(c.logical, |_| {});
                    });
                }
            });
            fm.i64(3, n as i64);
            fm.list_st(4, 1, |_, rg| {
                rg.list_st(1, chunks.len(), |i, cc| {
                    let (c, ch) = &chunks[i];
                    let next = chunks.get(i + 1).map_or(end, |x| x.1.start);
                    let size = (next - ch.start) as i64;
                    cc.i64(2, ch.start as i64);
                    cc.st(3, |m| {
                        m.i32(1, c.ty).list_i32(2, &ch.encodings).list_bin(3, &[c.name]).i32(4, 0);
                        m.i64(5, n as i64).i64(6, size).i64(7, size).i64(9, ch.data_off as i64);
                        if let Some(d) = ch.dict_off {
                            m.i64(11, d as i64);
                        }
                    });
                });
                rg.i64(2, (end - 4) as i64).i64(3, n as i64);
            });
            fm.bin(6, b"sessions direct writer");
            fm.out.push(0);
        }
        let meta_len = (self.out.len() - meta_at) as u32;
        self.out.extend_from_slice(&meta_len.to_le_bytes());
        self.out.extend_from_slice(b"PAR1");
        self.out
    }
}

/// Appends a PLAIN BYTE_ARRAY value (length prefix + bytes).
fn plain_bytes(dict: &mut Vec<u8>, b: &[u8]) {
    dict.extend_from_slice(&(b.len() as u32).to_le_bytes());
    dict.extend_from_slice(b);
}

/// The user_daily file for `rows` (non-empty). `id_bytes(key, buf)` appends a
/// person's user_id bytes to `buf`; `cat_names` are the output category strings.
pub(crate) fn user_daily(rows: &[UserRow], cat_names: &[&[u8]], mut id_bytes: impl FnMut(u64, &mut Vec<u8>)) -> Vec<u8> {
    let n = rows.len();
    assert!(n > 0);
    let mut f = File::new(n, n * 12 + (64 << 10));

    // user_id: one dictionary entry per run of equal persons
    let mut dict = Vec::with_capacity(n * 16);
    let mut idx = Vec::with_capacity(n);
    let (mut prev, mut k) = (None, 0u32);
    for p in rows.iter().map(|r| r.person) {
        if prev != Some(p) {
            if prev.is_some() {
                k += 1;
            }
            let at = dict.len();
            dict.extend_from_slice(&[0; 4]);
            id_bytes(p, &mut dict);
            let len = (dict.len() - at - 4) as u32;
            dict[at..at + 4].copy_from_slice(&len.to_le_bytes());
            prev = Some(p);
        }
        idx.push(k);
    }
    f.dict(col(b"user_id", STR.0, REQUIRED, STR.1, STR.2), &dict, k as usize + 1, None, idx.iter().copied());
    f.days(col(b"day", DATE.0, REQUIRED, DATE.1, DATE.2), rows.iter().map(|r| r.day));
    let mut vals = Vec::with_capacity(n);
    for (name, get) in [
        (&b"sessions"[..], (|r: &UserRow| r.sessions) as fn(&UserRow) -> i64),
        (b"events", |r| r.events),
        (b"revenue_cents", |r| r.revenue),
    ] {
        vals.clear();
        vals.extend(rows.iter().map(get));
        f.delta(col(name, I64.0, REQUIRED, I64.1, I64.2), &vals);
    }
    // top_category: optional; dictionary of every category name
    dict.clear();
    for name in cat_names {
        plain_bytes(&mut dict, name);
    }
    let defs: Vec<bool> = rows.iter().map(|r| r.top.is_some()).collect();
    let present = defs.iter().filter(|&&d| d).count();
    let tops = ExactIter { it: rows.iter().filter_map(|r| r.top), left: present };
    f.dict(col(b"top_category", STR.0, OPTIONAL, STR.1, STR.2), &dict, cat_names.len(), Some(&defs), tops);
    f.finish()
}

/// The campaign_daily file. `rows`: (campaign index, day, [sessions, purchasing,
/// revenue, assisted]); `ids[c]` / `channels[c]` are campaign c's strings.
pub(crate) fn campaign_daily(rows: &[(u32, i32, [i64; 4])], ids: &[&[u8]], channels: &[&[u8]]) -> Vec<u8> {
    let n = rows.len();
    assert!(n > 0);
    let mut f = File::new(n, n * 16 + (64 << 10));
    for (name, strs) in [(&b"campaign_id"[..], ids), (b"channel", channels)] {
        let mut dict = Vec::with_capacity(strs.iter().map(|s| s.len() + 4).sum());
        for s in strs {
            plain_bytes(&mut dict, s);
        }
        f.dict(col(name, STR.0, REQUIRED, STR.1, STR.2), &dict, strs.len(), None, ExactIter { it: rows.iter().map(|r| r.0), left: n });
    }
    f.days(col(b"day", DATE.0, REQUIRED, DATE.1, DATE.2), rows.iter().map(|r| r.1));
    let mut vals = Vec::with_capacity(n);
    for (j, name) in [&b"sessions"[..], b"purchasing_sessions", b"revenue_cents", b"assisted_sessions"].into_iter().enumerate() {
        vals.clear();
        vals.extend(rows.iter().map(|r| r.2[j]));
        f.delta(col(name, I64.0, REQUIRED, I64.1, I64.2), &vals);
    }
    f.finish()
}

struct ExactIter<I> {
    it: I,
    left: usize,
}

impl<I: Iterator<Item = u32>> Iterator for ExactIter<I> {
    type Item = u32;
    fn next(&mut self) -> Option<u32> {
        let v = self.it.next()?;
        self.left -= 1;
        Some(v)
    }
    fn size_hint(&self) -> (usize, Option<usize>) {
        (self.left, Some(self.left))
    }
}

impl<I: Iterator<Item = u32>> ExactSizeIterator for ExactIter<I> {}

#[cfg(test)]
mod tests {
    use super::*;
    use arrow_array::cast::AsArray;
    use arrow_array::types::{Date32Type, Int64Type};
    use arrow_array::Array;
    use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

    fn roundtrip(rows: &[UserRow], cats: &[&[u8]]) {
        let name = |k: u64| format!("p{k:x}{}", "é".repeat((k % 5) as usize));
        let file = user_daily(rows, cats, |k, out| out.extend_from_slice(name(k).as_bytes()));
        let path = std::env::temp_dir().join(format!("pq-test-{}-{}.parquet", std::process::id(), rows.len()));
        std::fs::write(&path, file).unwrap();
        let reader = ParquetRecordBatchReaderBuilder::try_new(std::fs::File::open(&path).unwrap()).unwrap().build().unwrap();
        let mut i = 0;
        for b in reader {
            let b = b.unwrap();
            let (uid, top) = (b.column(0).as_string::<i32>(), b.column(5).as_string::<i32>());
            let day = b.column(1).as_primitive::<Date32Type>();
            let cols: Vec<_> = (2..5).map(|c| b.column(c).as_primitive::<Int64Type>()).collect();
            for j in 0..b.num_rows() {
                let r = &rows[i];
                assert_eq!(uid.value(j), name(r.person), "row {i}");
                assert_eq!(day.value(j), r.day);
                assert_eq!([cols[0].value(j), cols[1].value(j), cols[2].value(j)], [r.sessions, r.events, r.revenue], "row {i}");
                match r.top {
                    None => assert!(top.is_null(j)),
                    Some(t) => assert_eq!(top.value(j).as_bytes(), cats[t as usize]),
                }
                i += 1;
            }
        }
        assert_eq!(i, rows.len());
        std::fs::remove_file(&path).unwrap();
    }

    #[test]
    fn direct_writer_roundtrips() {
        let cats: Vec<&[u8]> = vec![b"books", b"\xc3\xa9t\xc3\xa9", b"", b"unknown"];
        let mut x = 0x9e37_79b9_7f4a_7c15u64;
        let mut next = move || {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            x
        };
        let extremes = [0, 1, -1, i64::MAX, i64::MIN, i64::MAX - 1, i64::MIN + 1, 1 << 40];
        for n in [1usize, 2, 3, 7, 8, 9, 31, 32, 33, 127, 128, 129, 130, 255, 256, 257, 1000, 5000] {
            for mode in 0..4 {
                let mut rows = Vec::with_capacity(n);
                let mut person = 0u64;
                for i in 0..n {
                    if next() % 3 == 0 {
                        person += 1 + next() % 3;
                    }
                    let v = |r: u64| -> i64 {
                        match mode {
                            0 => (r % 4) as i64,
                            1 => (r % 10_000_000) as i64,
                            2 => extremes[(r % 8) as usize],
                            _ => r as i64,
                        }
                    };
                    rows.push(UserRow {
                        person,
                        day: 20_000 + (next() % 15) as i32 - if mode == 2 { 30_000 } else { 0 },
                        sessions: v(next()),
                        events: if mode == 0 { i as i64 } else { v(next()) },
                        revenue: v(next()),
                        top: (next() % 3 != 0).then(|| (next() % cats.len() as u64) as u32),
                    });
                }
                roundtrip(&rows, &cats);
            }
        }
        // all null, single category, single day, one person
        let rows: Vec<UserRow> = (0..300).map(|i| UserRow { person: 7, day: 5, sessions: 1, events: i, revenue: 0, top: None }).collect();
        roundtrip(&rows, &[b"unknown"]);
    }
}
