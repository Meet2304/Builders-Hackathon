#![allow(dead_code)]
use std::collections::HashMap;
pub const DAY_MS: i64 = 86_400_000;
pub const SYM: [u8; 256] = {
    let mut t = [0u8; 256];
    let mut i = 0;
    while i < 10 {
        t[b'0' as usize + i] = 1 + i as u8;
        i += 1;
    }
    i = 0;
    while i < 26 {
        t[b'A' as usize + i] = 11 + i as u8;
        t[b'a' as usize + i] = 38 + i as u8;
        i += 1;
    }
    t[b'_' as usize] = 37;
    t
};

const DESYM: [u8; 64] = {
    let mut t = [0u8; 64];
    let mut c = 0;
    while c < 256 {
        if SYM[c] != 0 {
            t[SYM[c] as usize] = c as u8;
        }
        c += 1;
    }
    t
};

/// 1..=10 packable chars -> key with char i in bits (63-6i)..(58-6i), zero padding, low
/// nibble 0. Zero padding sorts before every symbol, so u64 order == byte-wise order.
#[inline]
pub fn pack(b: &[u8]) -> Option<u64> {
    if b.is_empty() || b.len() > 10 {
        return None;
    }
    let mut k = 0u64;
    for (i, &c) in b.iter().enumerate() {
        let s = SYM[c as usize];
        if s == 0 {
            return None;
        }
        k |= (s as u64) << (58 - 6 * i);
    }
    Some(k)
}
pub fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

#[inline]
pub fn dig2(s: &[u8], i: usize) -> Option<i64> {
    let (a, b) = (s[i].wrapping_sub(b'0'), s[i + 1].wrapping_sub(b'0'));
    if a < 10 && b < 10 { Some((a * 10 + b) as i64) } else { None }
}

/// s[0..19] = `YYYY-MM-DDTHH:MM:SS` -> epoch ms.
#[inline]
pub fn parse_datetime(s: &[u8]) -> Option<i64> {
    if s[4] != b'-' || s[7] != b'-' || s[10] != b'T' || s[13] != b':' || s[16] != b':' {
        return None;
    }
    let y = dig2(s, 0)? * 100 + dig2(s, 2)?;
    let mo = dig2(s, 5)?;
    let d = dig2(s, 8)?;
    let h = dig2(s, 11)?;
    let mi = dig2(s, 14)?;
    let se = dig2(s, 17)?;
    if !(1..=12).contains(&mo) || d < 1 || h > 23 || mi > 59 || se > 59 {
        return None;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let dim = match mo {
        2 => if leap { 29 } else { 28 },
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    if d > dim {
        return None;
    }
    Some(((days_from_civil(y, mo, d) * 24 + h) * 60 + mi) * 60_000 + se * 1000)
}

/// F1 / F2 / F3 -> epoch ms. None = bad. F3 values beyond i64 map to i64::MAX
/// (outside every window, which is what the rules ask).
#[inline]
pub fn parse_ts(s: &[u8]) -> Option<i64> {
    let n = s.len();
    if n == 0 {
        return None;
    }
    if s[0].is_ascii_digit() && s[n - 1].is_ascii_digit() && s.iter().all(|c| c.is_ascii_digit()) {
        // F3 (an F1/F2 string always contains '-' so it can't land here)
        let mut v: u64 = 0;
        for &c in s {
            match v.checked_mul(10).and_then(|x| x.checked_add((c - b'0') as u64)) {
                Some(x) => v = x,
                None => return Some(i64::MAX),
            }
        }
        return Some(if v > i64::MAX as u64 { i64::MAX } else { v as i64 });
    }
    if n == 20 && s[19] == b'Z' {
        return parse_datetime(s);
    }
    if n == 25 && (s[19] == b'+' || s[19] == b'-') && s[22] == b':' {
        let base = parse_datetime(s)?;
        let oh = dig2(s, 20)?;
        let om = dig2(s, 23)?;
        if oh > 23 || om > 59 {
            return None;
        }
        let off = (oh * 60 + om) * 60_000;
        return Some(if s[19] == b'+' { base - off } else { base + off });
    }
    None
}

// Window-local timestamp decoding, ported from Explorer's explore/window-timestamps
// (d1da46e, evals/explore/window-timestamps.md). F1/F2 dates within the window +-8 days
// come from a small table, the clock digits decode in parallel, and 13-digit F3 values
// decode 8 lanes at a time. Every miss, and every other form, goes to v1's parse_ts.

#[inline]
pub fn eight_digits(digits: u64) -> bool {
    const HIGH_NIBBLES: u64 = 0xf0f0_f0f0_f0f0_f0f0;
    const SIX: u64 = 0x0606_0606_0606_0606;
    // Each lane started as ASCII XOR '0'. Values 0..=9 keep a zero high
    // nibble after adding six, and any originally set high nibble also fails.
    (digits | digits.wrapping_add(SIX)) & HIGH_NIBBLES == 0
}

#[inline]
pub fn decimal_eight(digits: u64) -> u64 {
    let pairs = (digits * 10 + (digits >> 8)) & 0x00ff_00ff_00ff_00ff;
    let quads = (pairs * 100 + (pairs >> 16)) & 0x0000_ffff_0000_ffff;
    ((quads as u32) as u64) * 10_000 + (quads >> 32)
}

#[inline]
pub fn clock_ms(clock: u64) -> Option<i64> {
    let digits = clock ^ u64::from_le_bytes(*b"00:00:00");
    if !eight_digits(digits) || digits & 0x0000_ff00_00ff_0000 != 0 {
        return None;
    }
    let pairs = digits * 10 + (digits >> 8);
    let h = pairs as u8;
    let m = (pairs >> 24) as u8;
    let s = (pairs >> 48) as u8;
    if h > 23 || m > 59 || s > 59 {
        return None;
    }
    Some(((h as i64 * 60 + m as i64) * 60 + s as i64) * 1000)
}

// Inverse of days_from_civil, used once per cached calendar day.
pub fn civil_from_days(day: i64) -> (i64, i64, i64) {
    let z = day + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (era * 400 + yoe + i64::from(m <= 2), m, d)
}

#[derive(Clone, Copy, Default)]
pub struct CalendarDay {
    prefix: u64,
    midnight: i64,
}

pub struct TimestampDecoder {
    days: [CalendarDay; 512],
}

impl TimestampDecoder {
    pub fn new(start: i64, end: i64) -> Self {
        let mut decoder = Self { days: [CalendarDay::default(); 512] };
        // This covers click offsets, and the ordinary ingest dates around
        // the window. A miss still uses the general parser, even for ingest.
        let first = start.div_euclid(DAY_MS) - 8;
        let last = end.div_euclid(DAY_MS) + 8;
        if last - first > 48 {
            return decoder;
        }
        for day in first..=last {
            let (y, m, d) = civil_from_days(day);
            if !(0..=9999).contains(&y) {
                continue;
            }
            let date = format!("{y:04}-{m:02}-{d:02}");
            let bytes = date.as_bytes();
            let prefix = u64::from_le_bytes(bytes[..8].try_into().unwrap());
            let index = Self::index(bytes[6], bytes[8], bytes[9]);
            decoder.days[index] = CalendarDay { prefix, midnight: day * DAY_MS };
        }
        decoder
    }

    #[inline]
    fn index(month: u8, tens: u8, ones: u8) -> usize {
        (((month as usize) & 1) << 8) | (((tens as usize) & 15) << 4) | ((ones as usize) & 15)
    }

    #[inline]
    fn cached_datetime(&self, s: &[u8]) -> Option<i64> {
        let prefix = u64::from_le_bytes(s[..8].try_into().unwrap());
        let day = &self.days[Self::index(s[6], s[8], s[9])];
        // A matching slot checks the complete date: the prefix covers year,
        // month and dashes, and the index plus high nibbles checks day digits.
        if day.prefix == 0 || prefix != day.prefix
            || (s[8] & 0xf0) != b'0' || (s[9] & 0xf0) != b'0' || s[10] != b'T'
        {
            return None;
        }
        let clock = u64::from_le_bytes(s[11..19].try_into().unwrap());
        Some(day.midnight + clock_ms(clock)?)
    }

    #[inline]
    pub fn parse(&self, s: &[u8]) -> Option<i64> {
        match s.len() {
            20 if s[19] == b'Z' => {
                if let Some(ts) = self.cached_datetime(s) {
                    return Some(ts);
                }
            }
            25 if matches!(s[19], b'+' | b'-') && s[22] == b':' => {
                if let Some(ts) = self.cached_datetime(s) {
                    let (h, m) = (dig2(s, 20)?, dig2(s, 23)?);
                    if h > 23 || m > 59 {
                        return None;
                    }
                    let offset = (h * 60 + m) * 60_000;
                    return Some(if s[19] == b'+' { ts - offset } else { ts + offset });
                }
            }
            13 => {
                const ZEROES: u64 = u64::from_le_bytes(*b"00000000");
                let low = u64::from_le_bytes(s[5..13].try_into().unwrap()) ^ ZEROES;
                let high = (u64::from_le_bytes(s[..8].try_into().unwrap()) ^ ZEROES) & 0xff_ffff_ffff;
                if eight_digits(high) && eight_digits(low) {
                    // The first five digits were loaded with three zero lanes.
                    return Some((decimal_eight(high) * 100_000 + decimal_eight(low)) as i64);
                }
                return None;
            }
            _ => {}
        }
        parse_ts(s)
    }
}


/// Purchase price: ASCII digits only, value 1..=10_000_000.
#[inline]
pub fn parse_price(s: &[u8]) -> Option<u32> {
    if s.is_empty() {
        return None;
    }
    let mut v: u64 = 0;
    for &c in s {
        let d = c.wrapping_sub(b'0');
        if d >= 10 {
            return None;
        }
        v = v * 10 + d as u64;
        if v > 10_000_000 {
            return None; // out of range (whatever follows)
        }
    }
    if v >= 1 { Some(v as u32) } else { None }
}

// ------------------------------------------------------------------ lookups

/// Map from a small ID set (products, campaigns) to u32. An ID of the canonical form
/// `prefix` + decimal digits with no leading zero, value < 2^22, indexes an array;
/// every other ID (and all of them with SESSIONS_DEBUG_NO_FAST=1) goes to a hash map.
/// The canonical value is unique per string, so the split is exact.
pub struct IdIndex<'a> {
    prefix: &'static [u8],
    direct_on: bool,
    direct: Vec<u32>, // u32::MAX = absent
    map: HashMap<&'a [u8], u32>,
}

impl<'a> IdIndex<'a> {
    pub fn new(prefix: &'static [u8], direct_on: bool) -> Self {
        IdIndex { prefix, direct_on, direct: Vec::new(), map: HashMap::new() }
    }

    #[inline]
    pub fn direct_slot(&self, b: &[u8]) -> Option<usize> {
        if !self.direct_on || !b.starts_with(self.prefix) {
            return None;
        }
        let d = &b[self.prefix.len()..];
        if d.is_empty() || d.len() > 7 || (d[0] == b'0' && d.len() > 1) {
            return None;
        }
        let mut v = 0usize;
        for &c in d {
            let x = c.wrapping_sub(b'0');
            if x >= 10 {
                return None;
            }
            v = v * 10 + x as usize;
        }
        (v < 1 << 22).then_some(v)
    }

    #[inline]
    pub fn get(&self, b: &[u8]) -> Option<u32> {
        match self.direct_slot(b) {
            Some(v) => self.direct.get(v).copied().filter(|&x| x != u32::MAX),
            None => self.map.get(b).copied(),
        }
    }

    pub fn set(&mut self, b: &'a [u8], val: u32) {
        match self.direct_slot(b) {
            Some(v) => {
                if v >= self.direct.len() {
                    self.direct.resize(v + 1, u32::MAX);
                }
                self.direct[v] = val;
            }
            None => {
                self.map.insert(b, val);
            }
        }
    }
}
