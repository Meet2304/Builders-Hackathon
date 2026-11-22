//! The event CSV fast path. Each column's decoder identifies its own terminator.
//! The only speculative reads are within the current guarded chunk.

use super::{
    BAD_CLOCK, DAY_MS, EvOut, EvRec, EventValues, Ids, Layout, Lookups, PK_HI, PK_IDX, PK_LO,
    PK_OFF, Relaxed, STATS, STATS_ON, TimestampDecoder, Win, clock_millis, decimal_eight,
    decode_event, direct_clock, emit_event, fallback_timestamp, pk_place, split_fields,
};

#[cfg(target_arch = "aarch64")]
use std::arch::aarch64::*;
#[cfg(target_arch = "x86_64")]
use std::arch::x86_64::*;

const LINE_GUARD: usize = 192;
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
            }
            Self::first_pos(bad)
        }
    }

    #[inline(always)]
    fn is_hex<const PREFIX: bool>(self) -> bool {
        unsafe {
            let digits = vcleq_u8(vsubq_u8(self.0, vdupq_n_u8(b'0')), vdupq_n_u8(9));
            let letters = vcleq_u8(vsubq_u8(self.0, vdupq_n_u8(b'a')), vdupq_n_u8(5));
            let mut valid = vorrq_u8(digits, letters);
            if PREFIX {
                valid = vsetq_lane_u8(u8::MAX, valid, 0);
            }
            vminvq_u8(valid) == u8::MAX
        }
    }

    #[inline(always)]
    fn special_len<const IGNORE_OPEN_QUOTE: bool>(self) -> usize {
        unsafe {
            let comma = vceqq_u8(self.0, vdupq_n_u8(b','));
            let mut quote = vceqq_u8(self.0, vdupq_n_u8(b'"'));
            if IGNORE_OPEN_QUOTE {
                quote = vsetq_lane_u8(0, quote, 0);
            }
            let newline = vceqq_u8(self.0, vdupq_n_u8(b'\n'));
            Self::first_pos(vorrq_u8(vorrq_u8(comma, quote), newline))
        }
    }

    #[inline(always)]
    fn pack_id<const FIXED_LEN: usize>(self) -> Option<(usize, u64)> {
        unsafe {
            let v = self.0;
            let hi = vshrq_n_u8(v, 4);
            let lo = vandq_u8(v, vdupq_n_u8(15));
            let valid = vtstq_u8(
                vqtbl1q_u8(vld1q_u8(PK_LO.as_ptr()), lo),
                vqtbl1q_u8(vld1q_u8(PK_HI.as_ptr()), hi),
            );
            let n = if FIXED_LEN == 0 {
                Self::first_pos(vmvnq_u8(valid))
            } else {
                FIXED_LEN
            };
            let live = vcltq_u8(vld1q_u8(PK_IDX.as_ptr()), vdupq_n_u8(n as u8));
            if FIXED_LEN != 0 && vmaxvq_u8(vbicq_u8(live, valid)) != 0 {
                return None;
            }
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
    fn is_hex<const PREFIX: bool>(self) -> bool {
        unsafe {
            let digits = _mm_sub_epi8(self.0, _mm_set1_epi8(b'0' as i8));
            let letters = _mm_sub_epi8(self.0, _mm_set1_epi8(b'a' as i8));
            let limit =
                |x, max| _mm_cmpeq_epi8(_mm_subs_epu8(x, _mm_set1_epi8(max)), _mm_setzero_si128());
            let valid = _mm_movemask_epi8(_mm_or_si128(limit(digits, 9), limit(letters, 5)));
            (valid | i32::from(PREFIX)) == 0xffff
        }
    }

    #[inline(always)]
    fn special_len<const IGNORE_OPEN_QUOTE: bool>(self) -> usize {
        unsafe {
            let comma = _mm_cmpeq_epi8(self.0, _mm_set1_epi8(b',' as i8));
            let mut quote = _mm_cmpeq_epi8(self.0, _mm_set1_epi8(b'"' as i8));
            if IGNORE_OPEN_QUOTE {
                quote = _mm_and_si128(quote, _mm_set_epi64x(-1, -256));
            }
            let newline = _mm_cmpeq_epi8(self.0, _mm_set1_epi8(b'\n' as i8));
            (_mm_movemask_epi8(_mm_or_si128(_mm_or_si128(comma, quote), newline)) as u32
                | (1 << 16))
                .trailing_zeros() as usize
        }
    }

    #[inline(always)]
    fn pack_id<const FIXED_LEN: usize>(self) -> Option<(usize, u64)> {
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
            let n = if FIXED_LEN == 0 {
                (bad as u32 | (1 << 16)).trailing_zeros() as usize
            } else {
                if bad & ((1 << FIXED_LEN) - 1) != 0 {
                    return None;
                }
                FIXED_LEN
            };
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

struct Column {
    start: *const u8,
    quote: usize,
    bytes: Bytes,
}

#[derive(Clone, Copy)]
enum FieldId<'a> {
    Packed(u64),
    Long(&'a [u8; 33]),
}

impl<'a> FieldId<'a> {
    #[inline(always)]
    fn is_empty(self) -> bool {
        matches!(self, Self::Packed(0))
    }

    #[inline(always)]
    fn key(self, ids: &Ids<'a>) -> u64 {
        match self {
            Self::Packed(key) => key,
            Self::Long(field) => ids.pack_long(field),
        }
    }
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

#[inline(always)]
unsafe fn skip_ignored<const TERM: u8>(p: *const u8) -> Option<(bool, *const u8)> {
    unsafe {
        let bytes = Bytes::load(p);
        let end = bytes.special_len::<true>();
        if end == 16 {
            return None;
        }
        let quote = (bytes.words().0 as u8 == b'"') as usize;
        Some((end != quote, terminate::<TERM>(p.add(end), quote)?))
    }
}

/// The two common IDs have eight base-36 bytes each. Validate and pack both
/// together, keeping their exact order-preserving keys.
#[cfg(target_arch = "x86_64")]
#[inline(always)]
unsafe fn short_id_pair(p: *const u8) -> Option<(u64, u64, *const u8)> {
    unsafe {
        let eq = (*p == b'"') as usize;
        let eid = p.add(eq);
        if *eid != b'e' {
            return None;
        }
        let p = terminate::<b','>(eid.add(9), eq)?;
        let uq = (*p == b'"') as usize;
        let user = p.add(uq);
        if *user != b'u' {
            return None;
        }
        let next = terminate::<b','>(user.add(9), uq)?;
        let a = _mm_loadl_epi64(eid.add(1).cast());
        let b = _mm_loadl_epi64(user.add(1).cast());
        let chars = _mm_unpacklo_epi64(a, b);
        let alpha = _mm_cmpgt_epi8(chars, _mm_set1_epi8(b'9' as i8));
        let origins = _mm_xor_si128(_mm_set1_epi8(b'0' as i8), _mm_and_si128(alpha, _mm_set1_epi8((b'0' ^ b'a') as i8)));
        let limits = _mm_xor_si128(_mm_set1_epi8(9), _mm_and_si128(alpha, _mm_set1_epi8(9 ^ 25)));
        let delta = _mm_sub_epi8(chars, origins);
        let excess = _mm_subs_epu8(delta, limits);
        if _mm_movemask_epi8(_mm_cmpeq_epi8(excess, _mm_setzero_si128())) != 0xffff {
            return None;
        }
        let offsets = _mm_xor_si128(_mm_set1_epi8(1), _mm_and_si128(alpha, _mm_set1_epi8(1 ^ 38)));
        let codes = _mm_add_epi8(delta, offsets);
        let pairs = _mm_maddubs_epi16(codes, _mm_set1_epi16(0x0140));
        let quads = _mm_madd_epi16(pairs, _mm_set1_epi32(0x0001_1000));
        let order = _mm_setr_epi8(4, 5, 6, 0, 1, 2, -1, -1, 12, 13, 14, 8, 9, 10, -1, -1);
        let bits = _mm_slli_epi64(_mm_shuffle_epi8(quads, order), 10);
        let eid = _mm_cvtsi128_si64(bits) as u64 | (super::SYM[b'e' as usize] as u64) << 58;
        let user = _mm_cvtsi128_si64(_mm_srli_si128(bits, 8)) as u64 | (super::SYM[b'u' as usize] as u64) << 58;
        Some((eid, user, next))
    }
}

#[cfg(target_arch = "x86_64")]
#[cold]
#[inline(never)]
unsafe fn other_id_pair<'a>(p: *const u8) -> Option<(FieldId<'a>, FieldId<'a>, *const u8)> {
    unsafe {
        let (eid, p) = Column::open(p).id::<b'e'>()?;
        let (user, p) = Column::open(p).id::<b'u'>()?;
        Some((eid, user, p))
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
    unsafe fn id<'a, const PREFIX: u8>(&self) -> Option<(FieldId<'a>, *const u8)> {
        // A verified delimiter at the common width lets the next column's
        // address be computed independently of packing the nine symbols.
        if let Some(next) = unsafe { self.end::<b','>(9) }
            && let Some((_, key)) = self.bytes.pack_id::<9>()
        {
            return Some((FieldId::Packed(key), next));
        }
        // The first register covers the prefix and 15 hex digits. Read the
        // following 16 digits in one block and check the final digit separately.
        if let Some(next) = unsafe { self.end::<b','>(33) }
            && self.bytes.words().0 as u8 == PREFIX
            && self.bytes.is_hex::<true>()
            && unsafe { Bytes::load(self.start.add(16)) }.is_hex::<false>()
        {
            let last = unsafe { *self.start.add(32) };
            if last.wrapping_sub(b'0') <= 9 || last.wrapping_sub(b'a') <= 5 {
                return Some((
                    FieldId::Long(unsafe { &*self.start.cast::<[u8; 33]>() }),
                    next,
                ));
            }
        }
        let (len, key) = self.bytes.pack_id::<0>()?;
        if len > 10 {
            return None;
        }
        Some((FieldId::Packed(key), unsafe { self.end::<b','>(len)? }))
    }

    #[inline(always)]
    unsafe fn skip<const TERM: u8>(&self) -> Option<(usize, *const u8)> {
        let len = self.bytes.special_len::<false>();
        if len == 16 {
            return None;
        }
        Some((len, unsafe { self.end::<TERM>(len)? }))
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
    fn midnight(self, dec: &TimestampDecoder) -> Option<i64> {
        let (expected, midnight) = dec.ingest_days[TimestampDecoder::day_index(self.middle as u16)];
        (self.prefix == expected).then_some(midnight)
    }

    #[inline(always)]
    fn same_day(self, other: Self) -> bool {
        (self.prefix == other.prefix) & ((self.middle ^ other.middle) & 0x00ff_ffff == 0)
    }

    #[inline(always)]
    fn hour(self, dec: &TimestampDecoder) -> Option<i64> {
        let suffix = (self.prefix >> 40) | (self.middle << 24);
        let hour = dec.hours[TimestampDecoder::index(suffix)];
        ((self.prefix == hour.prefix) & (suffix == hour.suffix)).then_some(hour.base)
    }
}

enum EventTime {
    Date(Date, i64),
    Millis(i64),
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

#[inline(always)]
unsafe fn event_time(c: &Column, dec: &TimestampDecoder) -> Option<(EventTime, usize, *const u8)> {
    let (lo, hi) = c.bytes.words();
    if (lo >> 32) as u8 == b'-' {
        let date = unsafe { c.date(lo, hi)? };
        let (len, tz) = match date.zone {
            b'Z' => (20, 0),
            b'+' | b'-' => (25, unsafe { offset(c, dec, date.zone)? }),
            _ => return None,
        };
        Some((EventTime::Date(date, tz), len, unsafe {
            c.end::<b','>(len)?
        }))
    } else {
        let len = c.bytes.digit_len::<0>();
        let next = unsafe { c.end::<b','>(len)? };
        Some((
            EventTime::Millis(decimal_field(lo, hi, len, dec)),
            len,
            next,
        ))
    }
}

#[inline(always)]
unsafe fn timestamp_pair(
    dec: &TimestampDecoder,
    time: EventTime,
    event: &Column,
    event_len: usize,
    ingest: &Column,
    ingest_date: Date,
) -> (i64, i64) {
    let midnight = ingest_date.midnight(dec);
    let i = if let Some(midnight) = midnight {
        direct_clock::<false>(dec.table, ingest_date.clock, midnight)
    } else {
        fallback_timestamp(unsafe { std::slice::from_raw_parts(ingest.start, 20) })
    };
    let ts = match time {
        EventTime::Millis(ms) => ms,
        EventTime::Date(date, tz) => {
            if tz == i64::MAX {
                i64::MAX
            } else if event_len == 20
                && let Some(midnight) = midnight
                && date.same_day(ingest_date)
            {
                let ms = direct_clock::<false>(dec.table, date.clock, 0);
                if ms < BAD_CLOCK as i64 {
                    midnight + ms
                } else {
                    i64::MAX
                }
            } else if let Some(hour) = date.hour(dec) {
                // The field template already checked both clock separators.
                let ms = clock_millis::<false>(dec.table, date.clock >> 16, 0);
                if ms < BAD_CLOCK as i64 {
                    hour + ms - tz
                } else {
                    i64::MAX
                }
            } else {
                fallback_timestamp(unsafe { std::slice::from_raw_parts(event.start, event_len) })
            }
        }
    };
    (ts, i)
}

#[inline(always)]
unsafe fn category(c: &Column, len: usize, canonical: bool, lk: &Lookups) -> u32 {
    let lo = c.bytes.words().0;
    // The lookup table's direct form is canonical p + 1..=7 digits.
    // Noncanonical IDs must still go through the exact map.
    if canonical && (2..=8).contains(&len) && lk.products.direct_on {
        let n = len - 1;
        let digits = (lo >> 8) ^ 0x0030_3030_3030_3030;
        let digits = digits << ((8 - n) * 8);
        if n == 1 || (lo >> 8) as u8 != b'0' {
            let idx = decimal_eight(digits) as usize;
            if idx < 1 << 22 {
                return lk
                    .products
                    .direct
                    .get(idx)
                    .copied()
                    .filter(|&v| v != u32::MAX)
                    .unwrap_or(lk.unknown_cat);
            }
        }
    }
    lk.category(unsafe { std::slice::from_raw_parts(c.start, len) })
}

#[inline(always)]
fn price(c: &Column, len: usize) -> u32 {
    if len == 0 {
        return 0;
    }
    let value = decimal_prefix(c.bytes.words().0, len) as u32;
    if value > 10_000_000 { 0 } else { value }
}

/// Requires LINE_GUARD bytes starting at p. The longest successful advances
/// are 36 + 36 + 28 + 23 + 18 + 19 + 19 bytes, including quotes and delimiters.
/// A failed field causes an immediate return, so the same bound covers failures.
/// Any raw field referenced by the interner must live as long as the lookups.
#[inline(always)]
unsafe fn try_line<'a>(
    p: *const u8,
    lk: &Lookups<'a>,
    w: &Win,
    dec: &TimestampDecoder,
) -> Option<(*const u8, Option<EvRec>)> {
    unsafe {
        #[cfg(target_arch = "x86_64")]
        let (eid, user, p) = if let Some((eid, user, p)) = short_id_pair(p) {
            (FieldId::Packed(eid), FieldId::Packed(user), p)
        } else {
            other_id_pair(p)?
        };
        #[cfg(target_arch = "aarch64")]
        let (eid, user, p) = {
            let (eid, p) = Column::open(p).id::<b'e'>()?;
            let (user, p) = Column::open(p).id::<b'u'>()?;
            (eid, user, p)
        };
        let event = Column::open(p);
        let (event_time, event_len, p) = event_time(&event, dec)?;
        let ing = Column::open(p);
        let (lo, hi) = ing.bytes.words();
        let date = ing.date(lo, hi)?;
        if date.zone != b'Z' {
            return None;
        }
        let p = ing.end::<b','>(20)?;

        let kind = Column::open(p);
        let k = kind.bytes.words().0;
        let (kind_len, purchase, valid_type) = if k == u64::from_le_bytes(*b"purchase") {
            (8, true, true)
        } else if k as u32 == u32::from_le_bytes(*b"view")
            || k as u32 == u32::from_le_bytes(*b"cart")
        {
            (4, false, true)
        } else {
            (kind.bytes.special_len::<false>(), false, false)
        };
        if kind_len == 16 {
            return None;
        }
        let p = kind.end::<b','>(kind_len)?;

        let (ts, ingest) = timestamp_pair(dec, event_time, &event, event_len, &ing, date);
        let valid_time_user = !eid.is_empty()
            && !user.is_empty()
            && ts >= w.start
            && ts < w.end
            && ingest.saturating_sub(ts) <= DAY_MS;
        let (next, row) = if purchase {
            let prod = Column::open(p);
            let (prod_len, product_digits, p) = if prod.bytes.words().0 as u8 == b'p' {
                let len = prod.bytes.digit_len::<1>();
                if let Some(p) = prod.end::<b','>(len) {
                    (len, true, p)
                } else {
                    let (len, p) = prod.skip::<b','>()?;
                    (len, false, p)
                }
            } else {
                let (len, p) = prod.skip::<b','>()?;
                (len, false, p)
            };
            let raw_price = Column::open(p);
            let len = raw_price.bytes.digit_len::<0>();
            let (price, next) = if let Some(p) = raw_price.end::<b'\n'>(len) {
                // More than eight digits can be valid with leading zeros.
                if len > 8 {
                    return None;
                }
                (price(&raw_price, len), p)
            } else {
                let (_, p) = raw_price.skip::<b'\n'>()?;
                (0, p)
            };
            let row = (valid_time_user && prod_len != 0 && price != 0).then(|| EventValues {
                user: user.key(&lk.ids),
                ts,
                price,
                cat: category(&prod, prod_len, product_digits, lk),
            });
            (next, row)
        } else {
            let (product, p) = skip_ignored::<b','>(p)?;
            let (_, next) = skip_ignored::<b'\n'>(p)?;
            let row = (valid_time_user && valid_type && product).then(|| EventValues {
                user: user.key(&lk.ids),
                ts,
                price: 0,
                cat: 0,
            });
            (next, row)
        };
        if eid.is_empty() {
            return Some((next, None));
        }
        Some((
            next,
            Some(EvRec {
                eid: eid.key(&lk.ids),
                ingest,
                row,
            }),
        ))
    }
}

#[cold]
#[inline(never)]
fn fallback<'a>(
    buf: &'a [u8],
    start: usize,
    end: usize,
    lk: &Lookups<'a>,
    w: &Win,
) -> (usize, Option<EvRec>) {
    let nl = memchr::memchr(b'\n', &buf[start..end]).map_or(end, |i| start + i);
    let mut fields = [&[][..]; 7];
    let rec = if split_fields(&buf[start..nl], &mut fields) {
        decode_event(&fields, lk, w)
    } else {
        None
    };
    (nl + 1, rec)
}

pub(super) fn parse_chunk<'a, L: Layout>(
    buf: &'a [u8],
    mut pos: usize,
    end: usize,
    lk: &Lookups<'a>,
    w: &Win,
    dec: &TimestampDecoder,
    out: &mut EvOut<L>,
) {
    let base = buf.as_ptr();
    let (mut fast, mut slow) = (0, 0);
    while pos < end {
        if end - pos >= LINE_GUARD {
            // SAFETY: the guard bounds all speculative reads from this line.
            if let Some((next, rec)) = unsafe { try_line(base.add(pos), lk, w, dec) } {
                if let Some(rec) = rec {
                    emit_event(rec, lk, out);
                }
                pos = unsafe { next.offset_from(base) } as usize;
                fast += 1;
                continue;
            }
        }
        let (next, rec) = fallback(buf, pos, end, lk, w);
        if let Some(rec) = rec {
            emit_event(rec, lk, out);
        }
        pos = next;
        slow += 1;
    }
    if STATS_ON.load(Relaxed) {
        STATS[7][0].fetch_add(fast, Relaxed);
        STATS[7][1].fetch_add(slow, Relaxed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Ids, Input, LinkTable, load_products, parse_ts};
    use std::path::Path;

    fn lookups(products: &[u8]) -> Lookups<'_> {
        let (products, cat_names) = load_products(products, true);
        Lookups {
            products,
            unknown_cat: cat_names.len() as u32,
            cat_names,
            cat_rank: Vec::new(),
            campaigns: crate::IdIndex::new(b"c_", true),
            camp_ids: Vec::new(),
            channels: Vec::new(),
            ids: Ids::new(0),
            links: LinkTable::new(0, u64::MAX),
            hmask: u64::MAX,
        }
    }

    fn window(start: i64, end: i64) -> Win {
        Win {
            start,
            end,
            ck_base: start.saturating_sub(crate::WEEK_MS),
            ckb: 16,
            decoder: Some(TimestampDecoder::new(start, end)),
        }
    }

    fn compare_line<'a>(
        buf: &'a [u8],
        pos: usize,
        nl: usize,
        end: usize,
        lk: &Lookups<'a>,
        w: &Win,
    ) -> bool {
        let mut fields = [&[][..]; 7];
        let expected = if split_fields(&buf[pos..nl], &mut fields) {
            decode_event(&fields, lk, w)
        } else {
            None
        };
        let decoded = if end - pos >= LINE_GUARD {
            // SAFETY: this is the same guard as parse_chunk.
            unsafe { try_line(buf.as_ptr().add(pos), lk, w, w.decoder.as_ref().unwrap()) }
        } else {
            None
        };
        let fast = decoded.is_some();
        let (next, got) = if let Some((next, got)) = decoded {
            (unsafe { next.offset_from(buf.as_ptr()) } as usize, got)
        } else {
            fallback(buf, pos, end, lk, w)
        };
        assert_eq!(
            (next, got),
            (nl + 1, expected),
            "at offset {pos}: {:?}",
            String::from_utf8_lossy(&buf[pos..nl])
        );
        fast
    }

    #[test]
    fn column_quotes_match_decoded_records() {
        let start = parse_ts(b"2026-10-01T00:00:00Z").unwrap();
        let w = window(start, start + 14 * DAY_MS);
        let patterns: [[&[u8]; 7]; 11] = [
            [
                b"eA_09Zx9I",
                b"U_2a3Z_9k",
                b"2026-10-01T01:02:03Z",
                b"2026-10-01T01:03:01Z",
                b"view",
                b"p1",
                b"",
            ],
            [
                b"e2",
                b"u2",
                b"2026-10-01T01:02:03+00:30",
                b"2026-10-01T00:33:01Z",
                b"purchase",
                b"p01",
                b"0250",
            ],
            [
                b"e3",
                b"u3",
                b"1790816523000",
                b"2026-10-01T01:03:01Z",
                b"purchase",
                b"p1",
                b"10000000",
            ],
            [b"", b"", b"", b"2026-10-01T01:03:01Z", b"", b"", b""],
            [
                b"e4",
                b"",
                b"2026-10-01T01:02:03Z",
                b"2026-10-01T01:03:01Z",
                b"view",
                b"p1",
                b"",
            ],
            [
                b"e5",
                b"u5",
                b"2026-10-01T01:02:03Z",
                b"2026-10-01T01:03:01Z",
                b"purchase",
                b"p1",
                b"00000000001",
            ],
            [
                b"e6",
                b"u6",
                b"0001790816523000",
                b"2026-10-01T01:03:01Z",
                b"cart",
                b"anything",
                b"19.99",
            ],
            [
                b"e7",
                b"u7",
                b"2026-10-01T01:02:03-00:30",
                b"2026-10-01T01:33:01Z",
                b"purchase",
                b"p1",
                b"100",
            ],
            [
                b"e0123456789abcdef0123456789abcdef",
                b"uabcdef0123456789abcdef0123456789",
                b"2026-10-01T01:02:03Z",
                b"2026-10-01T01:03:01Z",
                b"view",
                b"p1",
                b"",
            ],
            [
                b"e0123456789abcdef0123456789abcdef",
                b"uabcdef0123456789abcdef0123456789",
                b"2026-10-01T25:02:03Z",
                b"2026-10-01T01:03:00Z",
                b"purchase",
                b"p01",
                b"350",
            ],
            [
                b"e0123456789abcdef0123456789abcdeF",
                b"uabcdef0123456789abcdef0123456789",
                b"2026-10-01T01:02:03Z",
                b"2026-10-01T01:03:01Z",
                b"view",
                b"p1",
                b"",
            ],
        ];
        let mut cases = Vec::new();
        let mut add = |mut line: Vec<u8>, pad, want| {
            let len = line.len();
            line.push(b'\n');
            if pad {
                line.resize(LINE_GUARD.max(line.len()), b'\n');
            }
            cases.push((line, len, want));
        };
        for (case, fields) in patterns.iter().enumerate() {
            for quotes in 0u8..128 {
                let mut line = Vec::new();
                for (i, &field) in fields.iter().enumerate() {
                    if i != 0 {
                        line.push(b',');
                    }
                    let quoted = quotes & (1 << i) != 0;
                    if quoted {
                        line.push(b'"');
                    }
                    line.extend_from_slice(field);
                    if quoted {
                        line.push(b'"');
                    }
                }
                add(line.clone(), true, Some(!matches!(case, 5 | 10)));
                for i in 0..=line.len() {
                    for byte in [b',', b'"', b'\r', b'g'] {
                        let mut inserted = line.clone();
                        inserted.insert(i, byte);
                        add(inserted, true, None);
                    }
                    if i < line.len() {
                        let mut deleted = line.clone();
                        deleted.remove(i);
                        add(deleted, true, None);
                    }
                }
                add(line, false, Some(false));
            }
        }
        let lk = lookups(b"product_id,category\np1,a\np01,b\n");
        for (buf, len, want) in &cases {
            let fast = compare_line(buf, 0, *len, buf.len(), &lk, &w);
            if let Some(want) = want {
                assert_eq!(fast, *want, "{:?}", String::from_utf8_lossy(&buf[..*len]));
            }
            if buf.len() == *len + 1 {
                assert!(!compare_line(&buf[..*len], 0, *len, *len, &lk, &w));
            }
        }
    }

    /// Run on the actual shard and chunk boundaries. Compare every physical
    /// data line, including malformed rows and the bounded tail fallback.
    #[test]
    #[ignore = "requires local dev and seed-42 data"]
    fn column_real_lines_match_decoded_records() {
        let path = std::env::var_os("SESSIONS_COLDEC_DATA").unwrap_or_else(|| "data".into());
        let root = Path::new(&path);
        for dataset in ["dev", "seed-42"] {
            let path = root.join(dataset);
            let products = std::fs::read(path.join("products.csv")).unwrap();
            let input = Input::open(&path.join("events"));
            let lk = lookups(&products);
            let manifest: serde_json::Value =
                serde_json::from_slice(&std::fs::read(path.join("manifest.json")).unwrap())
                    .unwrap();
            let date = |key| parse_ts(manifest[key].as_str().unwrap().as_bytes()).unwrap();
            let w = window(date("window_start"), date("window_end"));
            let (mut lines, mut fast) = (0, 0);
            for (file, start, end) in input.chunks(crate::DEFAULT_CHUNK) {
                let buf = &input.maps[file];
                let mut pos = start;
                while pos < end {
                    let nl = memchr::memchr(b'\n', &buf[pos..end]).map_or(end, |i| pos + i);
                    fast += usize::from(compare_line(buf, pos, nl, end, &lk, &w));
                    lines += 1;
                    pos = nl + 1;
                }
            }
            assert!(lines > 0);
            eprintln!(
                "{dataset} decoded {lines} lines exactly, fast={fast}, fallback={} ({:.4}%)",
                lines - fast,
                (lines - fast) as f64 * 100.0 / lines as f64
            );
        }
    }
}
