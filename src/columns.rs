//! Shared SIMD field primitives adapted from Sol's event decoder (b7ed7d8).
//! The caller guards the whole line once, before opening any columns.

use super::links::decode_link;
use super::{
    BAD_CLOCK, Ck, CkOut, IdIndex, Ids, Lookups, PK_HI, PK_IDX, PK_LO, PK_OFF, Relaxed, STATS,
    STATS_ON, TimestampDecoder, WEEK_MS, Win, clock_millis, decimal_eight, decode_click, pk_place,
    split_fields,
};

#[cfg(target_arch = "aarch64")]
use std::arch::aarch64::*;
#[cfg(target_arch = "x86_64")]
use std::arch::x86_64::*;

const DATE_TEMPLATE: [u8; 16] = *b"0000-00-00T00:00";
const DATE_LIMIT: [u8; 16] = [9, 9, 9, 9, 0, 9, 9, 0, 9, 9, 0, 9, 9, 0, 9, 9];
const DIGITS: [u8; 16] = [b'0'; 16];
const NINES: [u8; 16] = [9; 16];

#[cfg(target_arch = "aarch64")]
#[derive(Clone, Copy)]
struct Bytes(uint8x16_t);

#[cfg(target_arch = "x86_64")]
#[derive(Clone, Copy)]
struct Bytes(__m128i);

#[cfg(target_arch = "aarch64")]
impl Bytes {
    #[inline(always)]
    unsafe fn load(p: *const u8) -> Self {
        Self(unsafe { vld1q_u8(p) })
    }

    #[inline(always)]
    fn words(self) -> (u64, u64) {
        unsafe {
            let x = vreinterpretq_u64_u8(self.0);
            (vgetq_lane_u64(x, 0), vgetq_lane_u64(x, 1))
        }
    }

    #[inline(always)]
    fn first_pos(selected: uint8x16_t) -> usize {
        unsafe {
            vminvq_u8(vbslq_u8(
                selected,
                vld1q_u8(PK_IDX.as_ptr()),
                vdupq_n_u8(16),
            )) as usize
        }
    }

    #[inline(always)]
    fn difference(self, template: &[u8; 16], limit: &[u8; 16]) -> uint8x16_t {
        unsafe {
            vqsubq_u8(
                veorq_u8(self.0, vld1q_u8(template.as_ptr())),
                vld1q_u8(limit.as_ptr()),
            )
        }
    }

    #[inline(always)]
    fn is_date(self) -> bool {
        unsafe { vmaxvq_u8(self.difference(&DATE_TEMPLATE, &DATE_LIMIT)) == 0 }
    }

    #[inline(always)]
    fn digit_len<const PREFIX: usize>(self) -> usize {
        unsafe {
            let mut bad = vcgtq_u8(self.difference(&DIGITS, &NINES), vdupq_n_u8(0));
            if PREFIX == 1 {
                bad = vsetq_lane_u8(0, bad, 0);
            } else if PREFIX == 2 {
                bad = vreinterpretq_u8_u16(vsetq_lane_u16(0, vreinterpretq_u16_u8(bad), 0));
            }
            Self::first_pos(bad)
        }
    }

    #[inline(always)]
    fn is_hex<const SKIP_PREFIX: bool>(self) -> bool {
        unsafe {
            let digits = vcleq_u8(vsubq_u8(self.0, vdupq_n_u8(b'0')), vdupq_n_u8(9));
            let letters = vcleq_u8(vsubq_u8(self.0, vdupq_n_u8(b'a')), vdupq_n_u8(5));
            let mut valid = vorrq_u8(digits, letters);
            if SKIP_PREFIX {
                valid = vsetq_lane_u8(u8::MAX, valid, 0);
            }
            vminvq_u8(valid) == u8::MAX
        }
    }

    #[inline(always)]
    fn pack_id(self) -> Option<(usize, u64)> {
        unsafe {
            let v = self.0;
            let hi = vshrq_n_u8(v, 4);
            let lo = vandq_u8(v, vdupq_n_u8(15));
            let valid = vtstq_u8(
                vqtbl1q_u8(vld1q_u8(PK_LO.as_ptr()), lo),
                vqtbl1q_u8(vld1q_u8(PK_HI.as_ptr()), hi),
            );
            let n = Self::first_pos(vmvnq_u8(valid));
            if n > 10 {
                return None;
            }
            let live = vcltq_u8(vld1q_u8(PK_IDX.as_ptr()), vdupq_n_u8(n as u8));
            let code = vaddq_u8(v, vqtbl1q_u8(vld1q_u8(PK_OFF.as_ptr()), hi));
            let code = vsubq_u8(code, vandq_u8(vceqq_u8(v, vdupq_n_u8(b'_')), vdupq_n_u8(4)));
            let w16 = vreinterpretq_u16_u8(vandq_u8(code, live));
            let pairs = vsraq_n_u16(vandq_u16(vshlq_n_u16(w16, 6), vdupq_n_u16(0x0fc0)), w16, 8);
            let w32 = vreinterpretq_u32_u16(pairs);
            let quads = vreinterpretq_u64_u32(vsraq_n_u32(
                vandq_u32(vshlq_n_u32(w32, 12), vdupq_n_u32(0x00ff_f000)),
                w32,
                16,
            ));
            Some((
                n,
                pk_place(vgetq_lane_u64(quads, 0), vgetq_lane_u64(quads, 1)),
            ))
        }
    }
}

#[cfg(target_arch = "x86_64")]
impl Bytes {
    #[inline(always)]
    unsafe fn load(p: *const u8) -> Self {
        Self(unsafe { _mm_loadu_si128(p.cast()) })
    }

    #[inline(always)]
    fn words(self) -> (u64, u64) {
        unsafe {
            (
                _mm_cvtsi128_si64(self.0) as u64,
                _mm_cvtsi128_si64(_mm_srli_si128(self.0, 8)) as u64,
            )
        }
    }

    #[inline(always)]
    fn difference(self, template: &[u8; 16], limit: &[u8; 16]) -> __m128i {
        unsafe {
            let bytes = _mm_xor_si128(self.0, _mm_loadu_si128(template.as_ptr().cast()));
            _mm_subs_epu8(bytes, _mm_loadu_si128(limit.as_ptr().cast()))
        }
    }

    #[inline(always)]
    fn is_date(self) -> bool {
        unsafe {
            _mm_movemask_epi8(_mm_cmpeq_epi8(
                self.difference(&DATE_TEMPLATE, &DATE_LIMIT),
                _mm_setzero_si128(),
            )) == 0xffff
        }
    }

    #[inline(always)]
    fn digit_len<const PREFIX: usize>(self) -> usize {
        unsafe {
            let valid = _mm_movemask_epi8(_mm_cmpeq_epi8(
                self.difference(&DIGITS, &NINES),
                _mm_setzero_si128(),
            ));
            ((!valid as u32 & (u32::MAX << PREFIX)) | (1 << 16)).trailing_zeros() as usize
        }
    }

    #[inline(always)]
    fn is_hex<const SKIP_PREFIX: bool>(self) -> bool {
        unsafe {
            let in_range = |base: u8, limit: u8| {
                let bytes = _mm_sub_epi8(self.0, _mm_set1_epi8(base as i8));
                _mm_cmpeq_epi8(
                    _mm_subs_epu8(bytes, _mm_set1_epi8(limit as i8)),
                    _mm_setzero_si128(),
                )
            };
            let mask = _mm_movemask_epi8(_mm_or_si128(in_range(b'0', 9), in_range(b'a', 5)));
            mask | i32::from(SKIP_PREFIX) == 0xffff
        }
    }

    #[inline(always)]
    fn pack_id(self) -> Option<(usize, u64)> {
        unsafe {
            let v = self.0;
            let ld = |t: &[u8; 16]| _mm_loadu_si128(t.as_ptr().cast());
            let nib = _mm_set1_epi8(15);
            let hi = _mm_and_si128(_mm_srli_epi16(v, 4), nib);
            let lo = _mm_and_si128(v, nib);
            let cls = _mm_and_si128(
                _mm_shuffle_epi8(ld(&PK_LO), lo),
                _mm_shuffle_epi8(ld(&PK_HI), hi),
            );
            let bad = _mm_movemask_epi8(_mm_cmpeq_epi8(cls, _mm_setzero_si128()));
            let n = (bad as u32 | (1 << 16)).trailing_zeros() as usize;
            if n > 10 {
                return None;
            }
            let live = _mm_cmpgt_epi8(_mm_set1_epi8(n as i8), ld(&PK_IDX));
            let code = _mm_add_epi8(v, _mm_shuffle_epi8(ld(&PK_OFF), hi));
            let code = _mm_sub_epi8(
                code,
                _mm_and_si128(
                    _mm_cmpeq_epi8(v, _mm_set1_epi8(b'_' as i8)),
                    _mm_set1_epi8(4),
                ),
            );
            let code = _mm_and_si128(code, live);
            let pairs = _mm_maddubs_epi16(code, _mm_set1_epi16(0x0140));
            let quads = _mm_madd_epi16(pairs, _mm_set1_epi32(0x0001_1000));
            let lo = _mm_cvtsi128_si64(quads) as u64;
            let hi = _mm_cvtsi128_si64(_mm_srli_si128(quads, 8)) as u64;
            Some((n, pk_place(lo, hi)))
        }
    }
}

enum Id<'a> {
    Short(u64),
    Long(&'a [u8; LONG_ID_LEN]),
}

impl<'a> Id<'a> {
    #[inline(always)]
    fn is_empty(&self) -> bool {
        matches!(self, Self::Short(0))
    }

    #[inline(always)]
    fn key(self, ids: &Ids<'a>) -> u64 {
        match self {
            Self::Short(key) => key,
            Self::Long(bytes) => pack_long(bytes, ids),
        }
    }
}

const LONG_ID_LEN: usize = 33;

/// The same key `Ids::key` gives these bytes: the lock-free long-ID table, or the
/// interner when the value's probe window is full.
#[inline]
fn pack_long<'a>(bytes: &'a [u8; LONG_ID_LEN], ids: &Ids<'a>) -> u64 {
    ids.long_key(bytes).unwrap_or_else(|| ids.intern(bytes))
}

struct Column {
    start: *const u8,
    quote: usize,
    bytes: Bytes,
}

#[inline(always)]
unsafe fn terminate<const TERM: u8>(last: *const u8, quote: usize) -> Option<*const u8> {
    unsafe {
        let term = last.add(quote);
        if (*term == TERM) & ((quote == 0) | (*last == b'"')) {
            Some(term.add(1))
        } else {
            None
        }
    }
}

impl Column {
    #[inline(always)]
    unsafe fn open(p: *const u8) -> Self {
        unsafe {
            let quote = (*p == b'"') as usize;
            let start = p.add(quote);
            Self {
                start,
                quote,
                bytes: Bytes::load(start),
            }
        }
    }

    #[inline(always)]
    unsafe fn end<const TERM: u8>(&self, len: usize) -> Option<*const u8> {
        unsafe { terminate::<TERM>(self.start.add(len), self.quote) }
    }

    #[inline(always)]
    unsafe fn id<'a, const TERM: u8, const PREFIX: u8>(&self) -> Option<(Id<'a>, *const u8)> {
        if let Some((len, key)) = self.bytes.pack_id() {
            return Some((Id::Short(key), unsafe { self.end::<TERM>(len)? }));
        }
        unsafe { self.long_id::<TERM, PREFIX>() }
    }

    /// The caller's chunk guard covers the prefix, 32 hex digits and delimiters.
    /// The first register already contains the prefix and the first 15 digits.
    #[cold]
    #[inline(never)]
    unsafe fn long_id<'a, const TERM: u8, const PREFIX: u8>(&self) -> Option<(Id<'a>, *const u8)> {
        unsafe {
            if self.bytes.words().0 as u8 != PREFIX {
                return None;
            }
            let next = self.end::<TERM>(LONG_ID_LEN)?;
            let last = *self.start.add(32);
            if !self.bytes.is_hex::<true>()
                || !Bytes::load(self.start.add(16)).is_hex::<false>()
                || !matches!(last, b'0'..=b'9' | b'a'..=b'f')
            {
                return None;
            }
            Some((Id::Long(&*self.start.cast::<[u8; LONG_ID_LEN]>()), next))
        }
    }

    #[inline(always)]
    unsafe fn date(&self, lo: u64, hi: u64) -> Option<Date> {
        // The first 16 bytes are already in the field register. Only the
        // fixed-width tail needs a second, four-byte read.
        let tail = unsafe { self.start.add(16).cast::<u32>().read_unaligned() };
        let delta = (tail ^ 0x0030_303a) & 0x00ff_ffff;
        if !self.bytes.is_date() || (delta | (delta + 0x0006_0600)) & 0x00f0_f0ff != 0 {
            return None;
        }
        Some(Date {
            prefix: lo,
            middle: hi,
            clock: (hi >> 24) | ((tail & 0x00ff_ffff) as u64) << 40,
            zone: (tail >> 24) as u8,
        })
    }
}

#[derive(Clone, Copy)]
struct Date {
    prefix: u64,
    middle: u64,
    clock: u64,
    zone: u8,
}

impl Date {
    #[inline(always)]
    fn hour(self, dec: &TimestampDecoder) -> Option<i64> {
        let suffix = (self.prefix >> 40) | (self.middle << 24);
        let hour = dec.hours[TimestampDecoder::index(suffix)];
        ((self.prefix == hour.prefix) & (suffix == hour.suffix)).then_some(hour.base)
    }
}

#[inline(always)]
fn decimal_prefix(word: u64, len: usize) -> u64 {
    // len is 1..=8. Shift the unused later bytes out and pad with zero digits.
    decimal_eight((word ^ 0x3030_3030_3030_3030) << ((8 - len) * 8))
}

#[inline(always)]
fn decimal_field(lo: u64, hi: u64, len: usize, dec: &TimestampDecoder) -> i64 {
    const POW10: [u64; 9] = [
        1,
        10,
        100,
        1000,
        10_000,
        100_000,
        1_000_000,
        10_000_000,
        100_000_000,
    ];
    if len == 13 {
        let prefix = lo & 0xff_ffff_ffff;
        let (expected, base) = dec.numeric[TimestampDecoder::numeric_index(prefix)];
        let high = if prefix == expected {
            base
        } else {
            (decimal_prefix(lo, 5) * 100_000_000) as i64
        };
        let b = decimal_prefix((lo >> 40) | (hi << 24), 8);
        return high + b as i64;
    }
    if len == 0 {
        i64::MAX
    } else if len <= 8 {
        decimal_prefix(lo, len) as i64
    } else {
        let rest = len - 8;
        (decimal_prefix(lo, 8) * POW10[rest] + decimal_prefix(hi, rest)) as i64
    }
}

#[inline(always)]
unsafe fn offset(c: &Column, dec: &TimestampDecoder, sign: u8) -> Option<i64> {
    unsafe {
        let bytes = c.start.add(20).cast::<u32>().read_unaligned();
        let last = *c.start.add(24);
        let delta = bytes ^ 0x303a_3030;
        if (delta | delta.wrapping_add(0x0600_0606)) & 0xf0ff_f0f0 != 0
            || last.wrapping_sub(b'0') > 9
        {
            return None;
        }
        let ms = dec.table[bytes as u16 as usize]
            + dec.table[65_536 | (((bytes >> 24) as usize) | ((last as usize) << 8))];
        Some(if ms >= BAD_CLOCK {
            i64::MAX
        } else if sign == b'+' {
            ms as i64
        } else {
            -(ms as i64)
        })
    }
}

/// A canonical campaign ID can be indexed from the field register. A noncanonical
/// ID (including a valid catalog entry) goes through the exact row decoder.
#[inline(always)]
unsafe fn campaign(c: &Column, campaigns: &IdIndex) -> Option<(Option<u32>, *const u8)> {
    let lo = c.bytes.words().0;
    if lo as u16 != u16::from_le_bytes(*b"c_") {
        return None;
    }
    let len = c.bytes.digit_len::<2>();
    if !(3..=8).contains(&len) || (len > 3 && (lo >> 16) as u8 == b'0') {
        return None;
    }
    // The eight-byte decimal word only contains six payload bytes after c_.
    // Seven-digit campaigns are rare and use the full IdIndex path.
    let next = unsafe { c.end::<b','>(len)? };
    let idx = decimal_prefix(lo >> 16, len - 2) as usize;
    Some((
        campaigns
            .direct
            .get(idx)
            .copied()
            .filter(|&x| x != u32::MAX),
        next,
    ))
}

#[inline(always)]
unsafe fn click_time(c: &Column, dec: &TimestampDecoder) -> Option<(i64, *const u8)> {
    let (lo, hi) = c.bytes.words();
    if (lo >> 32) as u8 == b'-' {
        let date = unsafe { c.date(lo, hi)? };
        let (len, tz) = match date.zone {
            b'Z' => (20, 0),
            b'+' | b'-' => (25, unsafe { offset(c, dec, date.zone)? }),
            _ => return None,
        };
        let next = unsafe { c.end::<b'\n'>(len)? };
        let hour = date.hour(dec)?;
        let ms = clock_millis::<false>(dec.table, date.clock >> 16, 0);
        if ms >= BAD_CLOCK as i64 || tz == i64::MAX {
            return None;
        }
        Some((hour + ms - tz, next))
    } else {
        let len = c.bytes.digit_len::<0>();
        if len == 0 {
            return None;
        }
        let next = unsafe { c.end::<b'\n'>(len)? };
        Some((decimal_field(lo, hi, len, dec), next))
    }
}

// A long quoted ID advances by 36 bytes. The campaign advances by at most
// 11 bytes and the timestamp can read through 27 bytes from its field start.
const CLICK_GUARD: usize = 112;
// The two long quoted IDs, including their separators, can consume 72 bytes.
const LINK_GUARD: usize = 72;

#[inline(always)]
unsafe fn click_line<'a>(
    p: *const u8,
    lk: &Lookups<'a>,
    w: &Win,
    dec: &TimestampDecoder,
) -> Option<(*const u8, Option<Ck>)> {
    unsafe {
        let (cid, p) = Column::open(p).id::<b',', b'k'>()?;
        let (person, p) = Column::open(p).id::<b',', b'u'>()?;
        let (camp, p) = campaign(&Column::open(p), &lk.campaigns)?;
        let (ts, next) = click_time(&Column::open(p), dec)?;
        let row = camp
            .filter(|_| {
                !cid.is_empty() && !person.is_empty() && ts >= w.start - WEEK_MS && ts < w.end
            })
            .map(|camp| Ck {
                cid: cid.key(&lk.ids),
                person: person.key(&lk.ids),
                camp,
                ts,
            });
        Some((next, row))
    }
}

#[inline(always)]
unsafe fn link_line<'a>(p: *const u8, ids: &Ids<'a>) -> Option<(*const u8, Option<(u64, u64)>)> {
    unsafe {
        let (a, p) = Column::open(p).id::<b',', b'u'>()?;
        let (b, next) = Column::open(p).id::<b'\n', b'u'>()?;
        let row = (!a.is_empty() && !b.is_empty()).then(|| (a.key(ids), b.key(ids)));
        Some((next, row))
    }
}

#[cold]
#[inline(never)]
fn fallback<'a, const N: usize, T>(
    buf: &'a [u8],
    start: usize,
    end: usize,
    decode: &impl Fn(&[&'a [u8]; N]) -> Option<T>,
) -> (usize, Option<T>) {
    let nl = memchr::memchr(b'\n', &buf[start..end]).map_or(end, |i| start + i);
    let mut fields = [&[][..]; N];
    let row = if split_fields(&buf[start..nl], &mut fields) {
        decode(&fields)
    } else {
        None
    };
    (nl + 1, row)
}

#[inline(always)]
fn for_each_decoded<'a, const N: usize, const GUARD: usize, T>(
    buf: &'a [u8],
    mut pos: usize,
    end: usize,
    fast: impl Fn(*const u8) -> Option<(*const u8, Option<T>)>,
    exact: impl Fn(&[&'a [u8]; N]) -> Option<T>,
    mut emit: impl FnMut(T),
) -> (u64, u64) {
    let base = buf.as_ptr();
    let (mut nfast, mut nslow) = (0, 0);
    while pos < end {
        if end - pos >= GUARD {
            // The whole-line guard bounds every speculative read by fast.
            if let Some((next, row)) = fast(unsafe { base.add(pos) }) {
                pos = unsafe { next.offset_from(base) } as usize;
                nfast += 1;
                if let Some(row) = row {
                    emit(row);
                }
                continue;
            }
        }
        let (next, row) = fallback(buf, pos, end, &exact);
        pos = next;
        nslow += 1;
        if let Some(row) = row {
            emit(row);
        }
    }
    (nfast, nslow)
}

pub(super) fn clicks<'a>(
    buf: &'a [u8],
    start: usize,
    end: usize,
    lk: &Lookups<'a>,
    w: &Win,
    dec: &TimestampDecoder,
    out: &mut CkOut,
) {
    let (fast, fallback) = for_each_decoded::<4, CLICK_GUARD, _>(
        buf,
        start,
        end,
        |p| unsafe { click_line(p, lk, w, dec) },
        |f| decode_click(f, lk, w),
        |c| out.queue(c, lk),
    );
    if STATS_ON.load(Relaxed) {
        STATS[4][0].fetch_add(fast, Relaxed);
        STATS[4][1].fetch_add(fallback, Relaxed);
    }
}

pub(super) fn links<'a>(
    buf: &'a [u8],
    start: usize,
    end: usize,
    ids: &Ids<'a>,
    out: &mut Vec<(u64, u64)>,
) {
    let (fast, fallback) = for_each_decoded::<2, LINK_GUARD, _>(
        buf,
        start,
        end,
        |p| unsafe { link_line(p, ids) },
        |f| decode_link(f, ids),
        |pair| out.push(pair),
    );
    if STATS_ON.load(Relaxed) {
        STATS[2][0].fetch_add(fast, Relaxed);
        STATS[2][1].fetch_add(fallback, Relaxed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Input, LinkTable, load_campaigns, parse_ts, read_small};
    use std::path::Path;

    fn lookups(campaigns: &[u8]) -> Lookups<'_> {
        let (campaigns, camp_ids, channels) = load_campaigns(campaigns, true);
        Lookups {
            products: IdIndex::new(b"p", true),
            cat_names: Vec::new(),
            cat_rank: Vec::new(),
            unknown_cat: 0,
            campaigns,
            camp_ids,
            channels,
            ids: Ids::new(0),
            links: LinkTable::new(0, u64::MAX),
            hmask: u64::MAX,
        }
    }

    fn window(start: i64, end: i64) -> Win {
        Win {
            start,
            end,
            decoder: Some(TimestampDecoder::new(start, end)),
        }
    }

    /// Compares the actual decoded values and the advancement, including lines
    /// that produce no row. Both paths share the interner for nonpackable IDs.
    fn compare_clicks<'a>(buf: &'a [u8], lk: &Lookups<'a>, w: &Win) -> (u64, u64) {
        let mut pos = 0;
        let mut rows = 0;
        let mut fast = 0;
        let dec = w.decoder.as_ref().unwrap();
        for line in buf.split_inclusive(|&c| c == b'\n') {
            let body = line.strip_suffix(b"\n").unwrap_or(line);
            let mut fields = [&[][..]; 4];
            let expected = split_fields(body, &mut fields)
                .then(|| decode_click(&fields, lk, w))
                .flatten();
            let p = unsafe { buf.as_ptr().add(pos) };
            let result = if buf.len() - pos >= CLICK_GUARD {
                unsafe { click_line(p, lk, w, dec) }
            } else {
                None
            };
            let actual = if let Some((next, row)) = result {
                fast += 1;
                assert_eq!(unsafe { next.offset_from(p) } as usize, line.len());
                row
            } else {
                let (next, row) = fallback(buf, pos, buf.len(), &|f| decode_click(f, lk, w));
                assert_eq!(next.min(buf.len()), pos + line.len());
                row
            };
            if actual != expected {
                panic!(
                    "decoded mismatch at byte {pos}, {:?}: {actual:?} != {expected:?}",
                    String::from_utf8_lossy(line)
                );
            }
            rows += 1;
            pos += line.len();
        }
        (rows, fast)
    }

    #[test]
    fn click_quote_and_timestamp_edges() {
        let catalog =
            b"campaign_id,channel\nc_10,search\nc_01,social\nC_10,email\nc_4194304,search\n";
        let start = parse_ts(b"2028-02-28T00:00:00Z").unwrap();
        let w = window(start, start + 14 * crate::DAY_MS);
        let ts = [
            b"2028-02-29T00:00:00Z".as_slice(),
            b"2028-02-28T19:00:00-05:00",
            b"2028-02-29T01:00:00+01:00",
            b"2028-02-21T00:00:00Z",
            b"2028-02-20T23:59:59Z",
            b"2028-02-30T00:00:00Z",
            b"2028-02-29T24:00:00Z",
            b"2028-02-29T00:00:60Z",
            b"2028-02-29T00:00:00+24:00",
            b"2028-02-29T00:00:00+05:60",
            b"2028-02-29T00:00:00+0500",
            b"2028-02-29t00:00:00Z",
            b"2028-02-29T00:00:00.000Z",
            b"2028-02-29T00:00:00Z\r",
            b"2028-02-29T00:00:00\nZ",
            b"000000000000000001835395200000",
            b"99999999999999999999999999999",
            b"",
        ];
        let f3 = (start + crate::DAY_MS + 987).to_string();
        let f3_padded = format!("000{f3}");
        let timestamp_cases = ts.into_iter().chain([f3.as_bytes(), f3_padded.as_bytes()]);
        for time in timestamp_cases {
            for mask in 0..16 {
                let mut line = Vec::new();
                for (i, f) in [b"k12345678".as_slice(), b"u12345678", b"c_10", time]
                    .into_iter()
                    .enumerate()
                {
                    let q = mask & (1 << i) != 0;
                    if q {
                        line.push(b'"');
                    }
                    line.extend_from_slice(f);
                    if q {
                        line.push(b'"');
                    }
                    line.push(if i == 3 { b'\n' } else { b',' });
                }
                // Pad past the line guard using complete empty lines.
                line.extend_from_slice(&[b'\n'; CLICK_GUARD]);
                let lk = lookups(catalog);
                let (_, fast) = compare_clicks(&line, &lk, &w);
                if [ts[0], ts[1], ts[2], f3.as_bytes(), f3_padded.as_bytes()].contains(&time) {
                    assert_eq!(
                        fast,
                        1,
                        "valid format {:?}, quote mask {mask}",
                        String::from_utf8_lossy(time)
                    );
                }
            }
        }
        let cases: &[&[u8]] = &[
            b"\"k12345678\",\"u12345678\",\"c_10\",\"2028-02-29T00:00:00Z\"",
            b"k123456789,u,c_01,2028-02-29T00:00:00Z",
            b"k1234567890,u,C_10,2028-02-29T00:00:00Z",
            b"k1, u,c_4194303,2028-02-29T00:00:00Z",
            b"k1,\" u\",c_4194304,2028-02-29T00:00:00Z",
            b"k1,\"u1\"\",c_10,2028-02-29T00:00:00Z",
            b"k1,\"u\"\"1\",c_10,2028-02-29T00:00:00Z",
            b"\"k1\",\"u,1\",c_10,2028-02-29T00:00:00Z",
            b"k1,u1,c_10,\"2028-02-29T00:00:00Z",
            b"k1,u1,c_10,2028-02-29T00:00:00Z\"",
            b"k1,u1,c_10,2028-02-29T00:00:00Z,",
            b"k1,u1,c_10",
            b"k1,\"\",c_10,2028-02-29T00:00:00Z",
            b"\",u1,c_10,2028-02-29T00:00:00Z",
            b"",
            b",,,",
        ];
        for &line in cases {
            let mut padded = line.to_vec();
            padded.extend_from_slice(&[b'\n'; CLICK_GUARD + 1]);
            let lk = lookups(catalog);
            compare_clicks(&padded, &lk, &w);
            compare_clicks(line, &lk, &w);
        }
    }

    #[test]
    fn long_click_and_link_ids() {
        let catalog = b"campaign_id,channel\nc_10,search\n";
        let start = parse_ts(b"2028-02-28T00:00:00Z").unwrap();
        let w = window(start, start + 14 * crate::DAY_MS);
        let click_id = b"k0123456789abcdef0123456789abcdef";
        let user_id = b"u9876543210abcdef9876543210abcdef";
        for mask in 0..16 {
            for (click, user) in [
                (&click_id[..], &user_id[..]),
                (&click_id[..], &b"user_1"[..]),
                (&b"click_1"[..], &user_id[..]),
            ] {
                let mut buf = Vec::new();
                for (i, field) in [click, user, b"c_10", b"2028-02-29T00:00:00Z"]
                    .into_iter()
                    .enumerate()
                {
                    let quote = (mask >> i) & 1 != 0;
                    if quote {
                        buf.push(b'"');
                    }
                    buf.extend_from_slice(field);
                    if quote {
                        buf.push(b'"');
                    }
                    buf.push(if i == 3 { b'\n' } else { b',' });
                }
                buf.extend_from_slice(&[b'\n'; CLICK_GUARD]);
                let lk = lookups(catalog);
                assert_eq!(compare_clicks(&buf, &lk, &w).1, 1);
            }
        }

        let mut link = [b'\n'; LINK_GUARD];
        link[0] = b'"';
        link[1..34].copy_from_slice(user_id);
        link[34..37].copy_from_slice(b"\",\"");
        link[37..70].copy_from_slice(user_id);
        link[70] = b'"';
        let ids = Ids::new(0);
        let (next, pair) = unsafe { link_line(link.as_ptr(), &ids) }.unwrap();
        assert_eq!(
            unsafe { next.offset_from(link.as_ptr()) } as usize,
            LINK_GUARD
        );
        let key = ids.key(user_id);
        assert_eq!(pair, Some((key, key)));

        for lane in 1..LONG_ID_LEN {
            let mut bad = link;
            for byte in [b'g', b'F', b'"', 0xff] {
                bad[1 + lane] = byte;
                assert!(
                    unsafe { Column::open(bad.as_ptr()).id::<b',', b'u'>() }.is_none(),
                    "lane {lane}, byte {byte}"
                );
            }
        }
    }

    #[test]
    fn link_quote_edges() {
        let mut buf = Vec::new();
        let ids = Ids::new(0);
        let lines: &[&[u8]] = &[
            b"u12345678,u87654321",
            b"\"u12345678\",u87654321",
            b"u12345678,\"u87654321\"",
            b"\"u12345678\",\"u87654321\"",
            b"u,USER_12345",
            b" A,\xe6\x97\xa5",
            b"a,b,c",
            b"a,b\r",
            b"\"\",b",
            b"\"a,b\"",
            b"\"a\"\"a\",b",
            b"a,b\"",
            b"a",
            b"",
            b",",
        ];
        let mut expected = Vec::new();
        for &line in lines.iter().cycle().take(lines.len() * 3) {
            let mut fields = [&[][..]; 2];
            if split_fields(line, &mut fields) {
                expected.extend(decode_link(&fields, &ids));
            }
            buf.extend_from_slice(line);
            buf.push(b'\n');
        }
        buf.extend_from_slice(b"\"tail\",nolf");
        expected.push((ids.key(b"tail"), ids.key(b"nolf")));
        let mut actual = Vec::new();
        links(&buf, 0, buf.len(), &ids, &mut actual);
        assert_eq!(actual, expected);
    }

    #[test]
    #[ignore = "requires the shared dev and seed-42 datasets"]
    fn decoded_clicks_match_dev_and_seed_42() {
        for dataset in ["data/dev", "data/seed-42"] {
            let root = Path::new(dataset);
            let catalog = read_small(&root.join("campaigns.csv"));
            let manifest: serde_json::Value =
                serde_json::from_slice(&read_small(&root.join("manifest.json"))).unwrap();
            let ts = |key: &str| parse_ts(manifest[key].as_str().unwrap().as_bytes()).unwrap();
            let w = window(ts("window_start"), ts("window_end"));
            let input = Input::open(&root.join("clicks"));
            let lk = lookups(&catalog);
            let (mut lines, mut fast) = (0, 0);
            for (fi, s, e) in input.chunks(4 << 20) {
                let (n, f) = compare_clicks(&input.maps[fi][s..e], &lk, &w);
                lines += n;
                fast += f;
            }
            assert!(lines > 250_000);
            eprintln!(
                "{dataset}: {lines} decoded click lines checked, {} fallbacks",
                lines - fast
            );
        }
    }
}
