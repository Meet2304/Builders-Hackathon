#![allow(dead_code)]
pub mod v3 {
pub fn split_fields<'a, const N: usize>(line: &'a [u8], out: &mut [&'a [u8]; N]) -> bool {
    if line.is_empty() {
        return false;
    }
    let mut n = 0;
    let mut start = 0;
    let mut i = 0;
    let len = line.len();
    loop {
        // find end of this field
        let mut quote = false;
        while i < len {
            let c = line[i];
            if c == b',' {
                break;
            }
            if c == b'"' {
                quote = true;
            }
            i += 1;
        }
        if n == N {
            return false; // too many fields
        }
        let mut f = &line[start..i];
        if quote {
            let fl = f.len();
            if fl < 2 || f[0] != b'"' || f[fl - 1] != b'"' || memchr::memchr(b'"', &f[1..fl - 1]).is_some() {
                return false;
            }
            f = &f[1..fl - 1];
        }
        out[n] = f;
        n += 1;
        if i >= len {
            break;
        }
        i += 1; // skip comma
        start = i;
        if i == len {
            // trailing comma: one more empty field
            if n == N {
                return false;
            }
            out[n] = &line[len..];
            n += 1;
            break;
        }
    }
    n == N
}

/// Iterate the lines of buf[start..end]. `end` is either buf.len() or just past a '\n'.
#[inline]
pub fn for_each_line<'a>(buf: &'a [u8], start: usize, end: usize, mut f: impl FnMut(&'a [u8])) {
    let mut p = start;
    while p < end {
        let nl = memchr::memchr(b'\n', &buf[p..end]).map_or(end, |i| p + i);
        f(&buf[p..nl]);
        p = nl + 1;
    }
}

/// How lines are split into fields.
#[derive(Clone, Copy, PartialEq)]
pub enum Scan {
    Simd,   // 64-byte classifier: NEON on aarch64, SSE2 on x86_64, SWAR elsewhere
    Swar,   // the portable u64 classifier everywhere (SESSIONS_DEBUG_NO_FAST=3)
    Scalar, // v1: memchr per line + split_fields (SESSIONS_DEBUG_NO_FAST=1)
}

/// SWAR: bit i set iff byte i of `w` equals `c` (exact, no false positives).
#[inline(always)]
pub fn swar_eq8(w: u64, c: u8) -> u64 {
    const LO7: u64 = 0x7f7f_7f7f_7f7f_7f7f;
    let x = w ^ (c as u64 * 0x0101_0101_0101_0101);
    // high bit of each byte set iff that byte of x is zero
    let z = !(((x & LO7) + LO7) | x | LO7);
    // gather the 8 high bits (bits 7, 15, ..., 63) into one byte
    ((z >> 7).wrapping_mul(0x0102_0408_1020_4080) >> 56) & 0xff
}

#[inline(always)]
pub fn classify_swar(p: &[u8; 64]) -> [u64; 3] {
    let mut m = [0u64; 3];
    for i in 0..8 {
        let w = u64::from_le_bytes(p[i * 8..i * 8 + 8].try_into().unwrap());
        m[0] |= swar_eq8(w, b'\n') << (i * 8);
        m[1] |= swar_eq8(w, b',') << (i * 8);
        m[2] |= swar_eq8(w, b'"') << (i * 8);
    }
    m
}

#[cfg(target_arch = "aarch64")]
#[inline(always)]
pub fn classify_simd(p: &[u8; 64]) -> [u64; 3] {
    use std::arch::aarch64::*;
    unsafe {
        let v = [vld1q_u8(p.as_ptr()), vld1q_u8(p.as_ptr().add(16)), vld1q_u8(p.as_ptr().add(32)), vld1q_u8(p.as_ptr().add(48))];
        const W: [u8; 16] = [1, 2, 4, 8, 16, 32, 64, 128, 1, 2, 4, 8, 16, 32, 64, 128];
        let w = vld1q_u8(W.as_ptr());
        let mask = |c: u8| -> u64 {
            let cv = vdupq_n_u8(c);
            let t: [uint8x16_t; 4] = std::array::from_fn(|i| vandq_u8(vceqq_u8(v[i], cv), w));
            let s0 = vpaddq_u8(t[0], t[1]);
            let s1 = vpaddq_u8(t[2], t[3]);
            let s = vpaddq_u8(s0, s1);
            let s = vpaddq_u8(s, s);
            vgetq_lane_u64(vreinterpretq_u64_u8(s), 0)
        };
        [mask(b'\n'), mask(b','), mask(b'"')]
    }
}

#[cfg(target_arch = "x86_64")]
#[inline(always)]
pub fn classify_simd(p: &[u8; 64]) -> [u64; 3] {
    // SSE2 is in every x86_64 CPU, so this path is the one the scorer runs AND the one
    // local x86-64-v2 emulation and Rosetta exercise.
    use std::arch::x86_64::*;
    unsafe {
        let v: [__m128i; 4] = std::array::from_fn(|i| _mm_loadu_si128(p.as_ptr().add(16 * i) as *const __m128i));
        let mask = |c: u8| -> u64 {
            let cv = _mm_set1_epi8(c as i8);
            let mut m = 0u64;
            for (i, x) in v.iter().enumerate() {
                m |= (_mm_movemask_epi8(_mm_cmpeq_epi8(*x, cv)) as u32 as u64) << (16 * i);
            }
            m
        };
        [mask(b'\n'), mask(b','), mask(b'"')]
    }
}

#[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
#[inline(always)]
pub fn classify_simd(p: &[u8; 64]) -> [u64; 3] {
    classify_swar(p)
}

/// Call `f` with the N fields of every well-formed line of buf[start..end] (`end` is
/// buf.len() or just past a '\n'). Exactly what for_each_line + split_fields accept:
/// a line with no '"' and exactly N-1 commas is sliced from the classifier's bitmasks;
/// every other line goes through split_fields.
#[inline]
pub fn for_each_record<'a, const N: usize>(buf: &'a [u8], start: usize, end: usize, scan: Scan, mut f: impl FnMut(&[&'a [u8]; N])) {
    let mut out = [&[][..]; N];
    if scan == Scan::Scalar {
        for_each_line(buf, start, end, |line| {
            if split_fields(line, &mut out) {
                f(&out);
            }
        });
        return;
    }
    let mut commas = [0usize; N];
    let mut ncomma = 0usize;
    let mut quoted = false;
    let mut ls = start;
    let mut emit = |ls: usize, le: usize, commas: &[usize; N], ncomma: usize, quoted: bool| {
        if !quoted && ncomma == N - 1 {
            let mut s = ls;
            for i in 0..N - 1 {
                out[i] = &buf[s..commas[i]];
                s = commas[i] + 1;
            }
            out[N - 1] = &buf[s..le];
            f(&out);
        } else if split_fields(&buf[ls..le], &mut out) {
            f(&out);
        }
    };
    let mut base = start;
    while base < end {
        let m = if base + 64 <= end {
            let blk: &[u8; 64] = buf[base..base + 64].try_into().unwrap();
            if scan == Scan::Simd { classify_simd(blk) } else { classify_swar(blk) }
        } else {
            let mut blk = [0u8; 64]; // zero bytes match nothing
            blk[..end - base].copy_from_slice(&buf[base..end]);
            if scan == Scan::Simd { classify_simd(&blk) } else { classify_swar(&blk) }
        };
        let mut bits = m[0] | m[1] | m[2];
        while bits != 0 {
            let b = bits.trailing_zeros();
            bits &= bits - 1;
            let pos = base + b as usize;
            if m[1] >> b & 1 != 0 {
                if ncomma < N {
                    commas[ncomma] = pos;
                }
                ncomma += 1;
            } else if m[0] >> b & 1 != 0 {
                emit(ls, pos, &commas, ncomma, quoted);
                ls = pos + 1;
                ncomma = 0;
                quoted = false;
            } else {
                quoted = true;
            }
        }
        base += 64;
    }
    if ls < end {
        emit(ls, end, &commas, ncomma, quoted);
    }
}

}
pub mod v4 {
use std::sync::atomic::{AtomicU64, AtomicBool, Ordering::Relaxed};
pub fn split_fields<'a, const N: usize>(line: &'a [u8], out: &mut [&'a [u8]; N]) -> bool {
    if line.is_empty() {
        return false;
    }
    let mut n = 0;
    let mut start = 0;
    let mut i = 0;
    let len = line.len();
    loop {
        // find end of this field
        let mut quote = false;
        while i < len {
            let c = line[i];
            if c == b',' {
                break;
            }
            if c == b'"' {
                quote = true;
            }
            i += 1;
        }
        if n == N {
            return false; // too many fields
        }
        let mut f = &line[start..i];
        if quote {
            let fl = f.len();
            if fl < 2 || f[0] != b'"' || f[fl - 1] != b'"' || memchr::memchr(b'"', &f[1..fl - 1]).is_some() {
                return false;
            }
            f = &f[1..fl - 1];
        }
        out[n] = f;
        n += 1;
        if i >= len {
            break;
        }
        i += 1; // skip comma
        start = i;
        if i == len {
            // trailing comma: one more empty field
            if n == N {
                return false;
            }
            out[n] = &line[len..];
            n += 1;
            break;
        }
    }
    n == N
}

/// Iterate the lines of buf[start..end]. `end` is either buf.len() or just past a '\n'.
#[inline]
pub fn for_each_line<'a>(buf: &'a [u8], start: usize, end: usize, mut f: impl FnMut(&'a [u8])) {
    let mut p = start;
    while p < end {
        let nl = memchr::memchr(b'\n', &buf[p..end]).map_or(end, |i| p + i);
        f(&buf[p..nl]);
        p = nl + 1;
    }
}

/// How lines are split into fields.
#[derive(Clone, Copy, PartialEq)]
pub enum Scan {
    Simd,   // 64-byte classifier: NEON on aarch64, SSE2 on x86_64, SWAR elsewhere
    Swar,   // the portable u64 classifier everywhere (SESSIONS_DEBUG_NO_FAST=3)
    Scalar, // v1: memchr per line + split_fields (SESSIONS_DEBUG_NO_FAST=1)
}

/// SWAR: bit i set iff byte i of `w` equals `c` (exact, no false positives).
#[inline(always)]
pub fn swar_eq8(w: u64, c: u8) -> u64 {
    const LO7: u64 = 0x7f7f_7f7f_7f7f_7f7f;
    let x = w ^ (c as u64 * 0x0101_0101_0101_0101);
    // high bit of each byte set iff that byte of x is zero
    let z = !(((x & LO7) + LO7) | x | LO7);
    // gather the 8 high bits (bits 7, 15, ..., 63) into one byte
    ((z >> 7).wrapping_mul(0x0102_0408_1020_4080) >> 56) & 0xff
}

#[inline(always)]
pub fn classify_swar(p: &[u8; 64]) -> [u64; 3] {
    let mut m = [0u64; 3];
    for i in 0..8 {
        let w = u64::from_le_bytes(p[i * 8..i * 8 + 8].try_into().unwrap());
        m[0] |= swar_eq8(w, b'\n') << (i * 8);
        m[1] |= swar_eq8(w, b',') << (i * 8);
        m[2] |= swar_eq8(w, b'"') << (i * 8);
    }
    m
}

#[cfg(target_arch = "aarch64")]
#[inline(always)]
pub fn classify_simd(p: &[u8; 64]) -> [u64; 3] {
    use std::arch::aarch64::*;
    unsafe {
        let v = [vld1q_u8(p.as_ptr()), vld1q_u8(p.as_ptr().add(16)), vld1q_u8(p.as_ptr().add(32)), vld1q_u8(p.as_ptr().add(48))];
        const W: [u8; 16] = [1, 2, 4, 8, 16, 32, 64, 128, 1, 2, 4, 8, 16, 32, 64, 128];
        let w = vld1q_u8(W.as_ptr());
        let mask = |c: u8| -> u64 {
            let cv = vdupq_n_u8(c);
            let t: [uint8x16_t; 4] = std::array::from_fn(|i| vandq_u8(vceqq_u8(v[i], cv), w));
            let s0 = vpaddq_u8(t[0], t[1]);
            let s1 = vpaddq_u8(t[2], t[3]);
            let s = vpaddq_u8(s0, s1);
            let s = vpaddq_u8(s, s);
            vgetq_lane_u64(vreinterpretq_u64_u8(s), 0)
        };
        [mask(b'\n'), mask(b','), mask(b'"')]
    }
}

#[cfg(target_arch = "x86_64")]
#[inline(always)]
pub fn classify_simd(p: &[u8; 64]) -> [u64; 3] {
    // SSE2 is in every x86_64 CPU, so this path is the one the scorer runs AND the one
    // local x86-64-v2 emulation and Rosetta exercise.
    use std::arch::x86_64::*;
    unsafe {
        let v: [__m128i; 4] = std::array::from_fn(|i| _mm_loadu_si128(p.as_ptr().add(16 * i) as *const __m128i));
        let mask = |c: u8| -> u64 {
            let cv = _mm_set1_epi8(c as i8);
            let mut m = 0u64;
            for (i, x) in v.iter().enumerate() {
                m |= (_mm_movemask_epi8(_mm_cmpeq_epi8(*x, cv)) as u32 as u64) << (16 * i);
            }
            m
        };
        [mask(b'\n'), mask(b','), mask(b'"')]
    }
}

#[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
#[inline(always)]
pub fn classify_simd(p: &[u8; 64]) -> [u64; 3] {
    classify_swar(p)
}

/// Call `f` with the N fields of every well-formed line of buf[start..end] (`end` is
/// buf.len() or just past a '\n'). Exactly what for_each_line + split_fields accept.
///
/// Fast path, from the classifier's bitmasks: a line with exactly N-1 commas whose every
/// '"' is accounted for by fields quoted end to end (a field starting with '"' of length
/// >= 2 that ends with '"' accounts for 2). split_fields splits on every comma and then
/// requires exactly that of each field containing a quote, so the fast path accepts the
/// same lines with the same (stripped) fields. Every other line goes to split_fields.
/// SESSIONS_DEBUG_STATS=1: lines taken by the fast path / by split_fields, per field count
/// N (2 = links, 4 = clicks, 7 = events), printed at exit. Counted per call, so the hot
/// loop only bumps two locals.
static STATS_ON: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
static STATS: [[AtomicU64; 2]; 8] = [const { [AtomicU64::new(0), AtomicU64::new(0)] }; 8];

#[inline]
pub fn for_each_record<'a, const N: usize>(buf: &'a [u8], start: usize, end: usize, scan: Scan, mut f: impl FnMut(&[&'a [u8]; N])) {
    let mut out = [&[][..]; N];
    if scan == Scan::Scalar {
        for_each_line(buf, start, end, |line| {
            if split_fields(line, &mut out) {
                f(&out);
            }
        });
        return;
    }
    let mut commas = [0usize; N];
    let mut ncomma = 0usize;
    let mut nquote = 0u32;
    let mut ls = start;
    let (mut n_fast, mut n_slow) = (0u64, 0u64);
    let mut emit = |ls: usize, le: usize, commas: &[usize; N], ncomma: usize, nquote: u32| {
        if ncomma == N - 1 {
            let mut s = ls;
            if nquote == 0 {
                for i in 0..N - 1 {
                    out[i] = &buf[s..commas[i]];
                    s = commas[i] + 1;
                }
                out[N - 1] = &buf[s..le];
                n_fast += 1;
                f(&out);
                return;
            }
            let mut counted = 0u32;
            for i in 0..N {
                let e = if i < N - 1 { commas[i] } else { le };
                let mut fld = &buf[s..e];
                if fld.len() >= 2 && fld[0] == b'"' && fld[fld.len() - 1] == b'"' {
                    fld = &fld[1..fld.len() - 1];
                    counted += 2;
                }
                out[i] = fld;
                s = e + 1;
            }
            if counted == nquote {
                n_fast += 1;
                f(&out);
                return;
            }
        }
        n_slow += 1;
        if split_fields(&buf[ls..le], &mut out) {
            f(&out);
        }
    };
    let mut base = start;
    while base < end {
        let m = if base + 64 <= end {
            let blk: &[u8; 64] = buf[base..base + 64].try_into().unwrap();
            if scan == Scan::Simd { classify_simd(blk) } else { classify_swar(blk) }
        } else {
            let mut blk = [0u8; 64]; // zero bytes match nothing
            blk[..end - base].copy_from_slice(&buf[base..end]);
            if scan == Scan::Simd { classify_simd(&blk) } else { classify_swar(&blk) }
        };
        // quotes are only counted, per line, by popcount of the bits before each newline
        let mut quotes = m[2];
        let mut bits = m[0] | m[1];
        while bits != 0 {
            let b = bits.trailing_zeros();
            bits &= bits - 1;
            let pos = base + b as usize;
            if m[1] >> b & 1 != 0 {
                if ncomma < N {
                    commas[ncomma] = pos;
                }
                ncomma += 1;
            } else {
                let below = (1u64 << b) - 1;
                nquote += (quotes & below).count_ones();
                quotes &= !below;
                emit(ls, pos, &commas, ncomma, nquote);
                ls = pos + 1;
                ncomma = 0;
                nquote = 0;
            }
        }
        nquote += quotes.count_ones();
        base += 64;
    }
    if ls < end {
        emit(ls, end, &commas, ncomma, nquote);
    }
    if STATS_ON.load(Relaxed) {
        STATS[N][0].fetch_add(n_fast, Relaxed);
        STATS[N][1].fetch_add(n_slow, Relaxed);
    }
}

}
