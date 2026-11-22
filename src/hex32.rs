//! Exact packer for the generator's long IDs: one prefix byte + 32 lowercase hex digits
//! (33 bytes, `docs/rules.md` line 101). One in eight distinct user, event and click IDs
//! has this form; the short packer (`pack`, <= 10 chars) can't hold them.
//!
//! ## API
//! - [`parse`]`(b) -> Option<(u8, u128)>`: `b` is exactly 33 bytes, `b[0]` is one of
//!   `c e k u`, and `b[1..33]` are all in `[0-9a-f]` -> `(b[0], value)`, where `value` is
//!   the 32 digits read as one big-endian 128-bit hex number. Anything else -> `None`
//!   (uppercase hex, any other byte, length 32 or 34, another prefix). The pair is an
//!   exact, invertible encoding of the string: [`write`] gives the bytes back.
//! - [`parse_with`]`(b, prefix) -> Option<u128>`: the same, but `b[0]` must equal `prefix`
//!   (the field's own prefix: `u` user, `e` event, `k` click). This is what a field parser
//!   wants: `Some(v)` means the key is `v` alone, since the prefix is fixed.
//! - [`write`]`(prefix, value, &mut [u8; 33])`: the inverse, for output.
//! - [`head_key`]`(prefix, value) -> u64`: the short packer's key of the ID's first 10
//!   bytes, for comparing with short packed IDs (see Ordering).
//! - [`self_test`]`() -> bool`: SIMD == scalar on about 17k inputs, for a startup guard
//!   like `pack_simd_self_test`.
//!
//! The data uses `u` (user), `e` (event) and `k` (click, not `c`). `c` is accepted too:
//! campaign IDs are `c_123`, so it costs nothing.
//!
//! ## Ordering (needed for the byte-wise smallest person name and the click tiebreak)
//! 1. Same prefix: `value` order == byte order of the strings. All 32 digits are present
//!    (fixed width), and digit order matches ASCII order (`'0'..'9'` < `'a'..'f'`).
//! 2. Different prefixes: the prefix byte decides (`c < e < k < u`); `value` never
//!    matters. [`tag2`] maps them to 0..=3 in that order, if you want them packed in 2 bits.
//! 3. Compared with a short packed ID `S` (1..=10 bytes, key `pack(S)` from `main.rs`), a
//!    long ID `H` is longer, so `S < H` iff `pack(S) <= head_key(H)`. `head_key(H)` is
//!    `pack(H[..10])`. If `pack(S)` equals it, `S == H[..10]` is a proper prefix of `H`.
//!    Otherwise the zero-padded keys differ at the first differing byte, exactly as the
//!    strings do. So `S > H` iff `pack(S) > head_key(H)`, and the two are never equal.
//! 4. Compared with an interned ID (uppercase, `_`, other widths): compare bytes, via
//!    [`write`].
//! Long and short IDs never collide: lengths 33 vs 1..=10.
//!
//! ## Cost
//! Both SIMD paths: two 16-byte loads, nibble/range classification, one horizontal test,
//! a pair-merge (NEON shift-insert / SSSE3 `pmaddubsw`), two byte swaps and a scalar
//! prefix lookup. No loop, no branch except the two exits. Measured numbers are in
//! `evals/explore/gemini-hex32.md`.

/// `b[0]` values accepted by [`parse`].
const PREFIX_OK: [bool; 256] = {
    let mut t = [false; 256];
    t[b'c' as usize] = true;
    t[b'e' as usize] = true;
    t[b'k' as usize] = true;
    t[b'u' as usize] = true;
    t
};

/// Digit value of `[0-9a-f]`; 0xff for every other byte (uppercase included).
const HEXVAL: [u8; 256] = {
    let mut t = [0xffu8; 256];
    let mut i = 0;
    while i < 10 {
        t[b'0' as usize + i] = i as u8;
        i += 1;
    }
    let mut i = 0;
    while i < 6 {
        t[b'a' as usize + i] = 10 + i as u8;
        i += 1;
    }
    t
};

/// Prefix byte -> 0..=3 in byte order (`c e k u`); only meaningful for accepted prefixes.
#[inline]
pub fn tag2(prefix: u8) -> u8 {
    match prefix {
        b'c' => 0,
        b'e' => 1,
        b'k' => 2,
        _ => 3,
    }
}

/// See the module docs.
#[inline(always)]
pub fn parse(b: &[u8]) -> Option<(u8, u128)> {
    if b.len() != 33 || !PREFIX_OK[b[0] as usize] {
        return None;
    }
    // SAFETY: b.len() == 33, so b[1..17] and b[17..33] are in bounds.
    unsafe { digits(b.as_ptr().add(1)) }.map(|v| (b[0], v))
}

/// See the module docs.
#[inline(always)]
pub fn parse_with(b: &[u8], prefix: u8) -> Option<u128> {
    if b.len() != 33 || b[0] != prefix {
        return None;
    }
    // SAFETY: as in `parse`.
    unsafe { digits(b.as_ptr().add(1)) }
}

/// Portable reference: the same contract as [`parse`].
pub fn parse_scalar(b: &[u8]) -> Option<(u8, u128)> {
    if b.len() != 33 || !PREFIX_OK[b[0] as usize] {
        return None;
    }
    let mut v = 0u128;
    for &c in &b[1..] {
        let d = HEXVAL[c as usize];
        if d == 0xff {
            return None;
        }
        v = v << 4 | d as u128;
    }
    Some((b[0], v))
}

const LOWER_HEX: &[u8; 16] = b"0123456789abcdef";

/// The 33 bytes of `(prefix, value)`.
#[inline]
pub fn write(prefix: u8, value: u128, out: &mut [u8; 33]) {
    out[0] = prefix;
    for i in 0..32 {
        out[1 + i] = LOWER_HEX[(value >> (124 - 4 * i)) as usize & 15];
    }
}

/// `main.rs` `pack` code of a hex digit: '0'..'9' -> 1..=10, 'a'..'f' -> 38..=43.
#[inline(always)]
fn sym_of_digit(d: u64) -> u64 {
    if d < 10 { d + 1 } else { d + 28 }
}

/// `pack` code of a prefix letter (`'a'` -> 38).
#[inline(always)]
fn sym_of_lower(c: u8) -> u64 {
    (c - b'a') as u64 + 38
}

/// `pack(H[..10])` for the long ID `H = (prefix, value)`. See Ordering in the module docs.
#[inline]
pub fn head_key(prefix: u8, value: u128) -> u64 {
    let mut k = sym_of_lower(prefix) << 58;
    for i in 0..9 {
        let d = (value >> (124 - 4 * i)) as u64 & 15;
        k |= sym_of_digit(d) << (52 - 6 * i);
    }
    k
}

/// Byte-wise order of short packed ID `s` (a `pack` key) vs long ID `(prefix, value)`.
#[inline]
pub fn cmp_short_long(s: u64, prefix: u8, value: u128) -> std::cmp::Ordering {
    if s <= head_key(prefix, value) { std::cmp::Ordering::Less } else { std::cmp::Ordering::Greater }
}

// ---- 32 digits at p -> u128 ----

/// Class bits by low nibble: 1 = 0..=9 (digits, row 3), 2 = 1..=6 (a..f, row 6).
const HX_LO: [u8; 16] = [1, 3, 3, 3, 3, 3, 3, 1, 1, 1, 0, 0, 0, 0, 0, 0];
/// Class bits allowed by high nibble: row 3 digits, row 6 lowercase letters, else none.
const HX_HI: [u8; 16] = [0, 0, 0, 1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0];
/// Value offset by high nibble: '0'..'9' -> low nibble, 'a'..'f' -> low nibble + 9.
const HX_OFF: [u8; 16] = [0, 0, 0, 0, 0, 0, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0];

/// SAFETY: `p..p+32` readable.
#[cfg(target_arch = "aarch64")]
#[inline(always)]
pub(crate) unsafe fn digits(p: *const u8) -> Option<u128> {
    use std::arch::aarch64::*;
    unsafe {
        let (tlo, thi, toff) = (vld1q_u8(HX_LO.as_ptr()), vld1q_u8(HX_HI.as_ptr()), vld1q_u8(HX_OFF.as_ptr()));
        let m15 = vdupq_n_u8(15);
        let a = vld1q_u8(p);
        let b = vld1q_u8(p.add(16));
        let (ah, al) = (vshrq_n_u8(a, 4), vandq_u8(a, m15));
        let (bh, bl) = (vshrq_n_u8(b, 4), vandq_u8(b, m15));
        let ok = vandq_u8(
            vtstq_u8(vqtbl1q_u8(tlo, al), vqtbl1q_u8(thi, ah)),
            vtstq_u8(vqtbl1q_u8(tlo, bl), vqtbl1q_u8(thi, bh)),
        );
        if vminvq_u8(ok) == 0 {
            return None;
        }
        let av = vaddq_u8(al, vqtbl1q_u8(toff, ah));
        let bv = vaddq_u8(bl, vqtbl1q_u8(toff, bh));
        // u16 lane = d_even | d_odd << 8  ->  low byte d_even << 4 | d_odd
        let (aw, bw) = (vreinterpretq_u16_u8(av), vreinterpretq_u16_u8(bv));
        let ap = vsraq_n_u16(vshlq_n_u16(aw, 4), aw, 8);
        let bp = vsraq_n_u16(vshlq_n_u16(bw, 4), bw, 8);
        // even bytes of both: the 16 value bytes, most significant first
        let bytes = vreinterpretq_u64_u8(vuzp1q_u8(vreinterpretq_u8_u16(ap), vreinterpretq_u8_u16(bp)));
        let hi = vgetq_lane_u64(bytes, 0).swap_bytes();
        let lo = vgetq_lane_u64(bytes, 1).swap_bytes();
        Some((hi as u128) << 64 | lo as u128)
    }
}

/// SAFETY: `p..p+32` readable.
#[cfg(all(target_arch = "x86_64", target_feature = "ssse3"))]
#[inline(always)]
pub(crate) unsafe fn digits(p: *const u8) -> Option<u128> {
    use std::arch::x86_64::*;
    unsafe {
        let ld = |t: &[u8; 16]| _mm_loadu_si128(t.as_ptr() as *const __m128i);
        let (tlo, thi, toff) = (ld(&HX_LO), ld(&HX_HI), ld(&HX_OFF));
        let m15 = _mm_set1_epi8(15);
        let a = _mm_loadu_si128(p as *const __m128i);
        let b = _mm_loadu_si128(p.add(16) as *const __m128i);
        let (ah, al) = (_mm_and_si128(_mm_srli_epi16(a, 4), m15), _mm_and_si128(a, m15));
        let (bh, bl) = (_mm_and_si128(_mm_srli_epi16(b, 4), m15), _mm_and_si128(b, m15));
        let ca = _mm_and_si128(_mm_shuffle_epi8(tlo, al), _mm_shuffle_epi8(thi, ah));
        let cb = _mm_and_si128(_mm_shuffle_epi8(tlo, bl), _mm_shuffle_epi8(thi, bh));
        let z = _mm_setzero_si128();
        let bad = _mm_or_si128(_mm_cmpeq_epi8(ca, z), _mm_cmpeq_epi8(cb, z));
        if _mm_movemask_epi8(bad) != 0 {
            return None;
        }
        let av = _mm_add_epi8(al, _mm_shuffle_epi8(toff, ah));
        let bv = _mm_add_epi8(bl, _mm_shuffle_epi8(toff, bh));
        // d_even * 16 + d_odd per u16 (<= 255), then pack both to 16 bytes, MSB first
        let w = _mm_set1_epi16(0x0110);
        let bytes = _mm_packus_epi16(_mm_maddubs_epi16(av, w), _mm_maddubs_epi16(bv, w));
        let hi = (_mm_cvtsi128_si64(bytes) as u64).swap_bytes();
        let lo = (_mm_cvtsi128_si64(_mm_srli_si128(bytes, 8)) as u64).swap_bytes();
        Some((hi as u128) << 64 | lo as u128)
    }
}

/// SAFETY: `p..p+32` readable.
#[cfg(not(any(target_arch = "aarch64", all(target_arch = "x86_64", target_feature = "ssse3"))))]
#[inline(always)]
pub(crate) unsafe fn digits(p: *const u8) -> Option<u128> {
    let s = unsafe { std::slice::from_raw_parts(p, 32) };
    let mut v = 0u128;
    for &c in s {
        let d = HEXVAL[c as usize];
        if d == 0xff {
            return None;
        }
        v = v << 4 | d as u128;
    }
    Some(v)
}

/// Startup guard: SIMD == scalar for every byte value at every digit position (and as
/// the prefix), on several bases. Lanes are classified independently, so this covers
/// every single-byte fault. About 17k checks, well under 1 ms.
pub fn self_test() -> bool {
    let bases: [&[u8; 33]; 3] = [
        b"u0123456789abcdef0123456789abcdef",
        b"efedcba9876543210fedcba9876543210",
        b"k00000000000000000000000000000000",
    ];
    for base in bases {
        if parse(base) != parse_scalar(base) || parse(base).is_none() {
            return false;
        }
        for pos in 0..33 {
            for c in 0..=255u8 {
                let mut s = *base;
                s[pos] = c;
                if parse(&s) != parse_scalar(&s) {
                    return false;
                }
            }
        }
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A random 33-byte valid ID from `x`.
    fn sample(prefix: u8, x: u128) -> [u8; 33] {
        let mut s = [0u8; 33];
        write(prefix, x, &mut s);
        s
    }

    fn mix(mut z: u64) -> u64 {
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    #[test]
    fn self_test_passes() {
        assert!(self_test());
    }

    #[test]
    fn roundtrip_and_value() {
        let s = b"u0123456789abcdef0123456789abcdef";
        let (p, v) = parse(s).unwrap();
        assert_eq!(p, b'u');
        assert_eq!(v, 0x0123456789abcdef0123456789abcdef);
        assert_eq!(parse_with(s, b'u'), Some(v));
        assert_eq!(parse_with(s, b'e'), None);
        for i in 0..20_000u64 {
            let x = (mix(i) as u128) << 64 | mix(!i) as u128;
            for pre in [b'c', b'e', b'k', b'u'] {
                let s = sample(pre, x);
                assert_eq!(parse(&s), Some((pre, x)));
                assert_eq!(parse_scalar(&s), Some((pre, x)));
                assert_eq!(parse_with(&s, pre), Some(x));
            }
        }
        assert_eq!(parse(&sample(b'u', 0)), Some((b'u', 0)));
        assert_eq!(parse(&sample(b'u', u128::MAX)), Some((b'u', u128::MAX)));
    }

    /// Every byte value at every position, on several bases; only the right classes pass.
    #[test]
    fn every_position_every_byte() {
        let bases: [&[u8; 33]; 4] = [
            b"u0123456789abcdef0123456789abcdef",
            b"efedcba9876543210fedcba9876543210",
            b"k00000000000000000000000000000000",
            b"cffffffffffffffffffffffffffffffff",
        ];
        for base in bases {
            for pos in 0..33 {
                for c in 0..=255u8 {
                    let mut s = *base;
                    s[pos] = c;
                    let want_ok = if pos == 0 {
                        matches!(c, b'c' | b'e' | b'k' | b'u')
                    } else {
                        c.is_ascii_digit() || (b'a'..=b'f').contains(&c)
                    };
                    let got = parse(&s);
                    assert_eq!(got, parse_scalar(&s), "pos {pos} byte {c:#x}");
                    assert_eq!(got.is_some(), want_ok, "pos {pos} byte {c:#x}");
                    if let Some((p, v)) = got {
                        let mut back = [0u8; 33];
                        write(p, v, &mut back);
                        assert_eq!(back, s);
                    }
                    if c.is_ascii_uppercase() && pos > 0 {
                        assert!(got.is_none(), "uppercase {c} at {pos} accepted");
                    }
                }
            }
        }
    }

    /// Two bad bytes at once (all position pairs, a few bad classes) are still rejected.
    #[test]
    fn pairs_of_bad_bytes() {
        let base = *b"u0123456789abcdef0123456789abcdef";
        for i in 1..33 {
            for j in i..33 {
                for bad in [b'A', b'F', b'g', b'/', b':', b'`', b'G', 0x80, 0xb0, 0xe6, b',', b'"'] {
                    let mut s = base;
                    s[i] = bad;
                    s[j] = bad;
                    assert_eq!(parse(&s), None);
                }
            }
        }
    }

    #[test]
    fn wrong_lengths_and_prefixes() {
        let long = b"u0123456789abcdef0123456789abcdef0";
        for n in 0..=long.len() {
            let got = parse(&long[..n]);
            assert_eq!(got.is_some(), n == 33, "len {n}");
            assert_eq!(parse_scalar(&long[..n]).is_some(), n == 33);
        }
        // 32 hex digits without a prefix, 33 with an uppercase / digit / other prefix
        assert_eq!(parse(b"0123456789abcdef0123456789abcdef"), None);
        for pre in [b'U', b'E', b'K', b'C', b'0', b'a', b'f', b'p', b'_', b' '] {
            let mut s = *b"u0123456789abcdef0123456789abcdef";
            s[0] = pre;
            assert_eq!(parse(&s), None, "prefix {}", pre as char);
        }
        // a short ID's bytes behind the slice end must not matter (slice, not buffer)
        let buf = b"uabc,0123456789abcdef0123456789abcdef";
        assert_eq!(parse(&buf[..4]), None);
    }

    /// Same prefix: u128 order == byte order. Across prefixes: the prefix byte decides.
    #[test]
    fn order_matches_bytes() {
        let mut ids = Vec::new();
        for i in 0..3000u64 {
            let mut x = (mix(i) as u128) << 64 | mix(i ^ 0x55) as u128;
            if i % 3 == 0 {
                x &= !0xffff_ffff_u128 << 96; // shared leading digits
            }
            ids.push(sample([b'c', b'e', b'k', b'u'][(i % 4) as usize], x));
        }
        let key = |s: &[u8; 33]| {
            let (p, v) = parse(s).unwrap();
            (tag2(p), v)
        };
        for a in ids.iter().step_by(7) {
            for b in &ids {
                assert_eq!(key(a).cmp(&key(b)), a.as_slice().cmp(b.as_slice()));
            }
        }
    }

    /// The short packer from main.rs, copied, for the cross-width order check.
    fn pack(b: &[u8]) -> Option<u64> {
        if b.is_empty() || b.len() > 10 {
            return None;
        }
        let mut k = 0u64;
        for (i, &c) in b.iter().enumerate() {
            let s = match c {
                b'0'..=b'9' => c - b'0' + 1,
                b'A'..=b'Z' => c - b'A' + 11,
                b'_' => 37,
                b'a'..=b'z' => c - b'a' + 38,
                _ => return None,
            };
            k |= (s as u64) << (58 - 6 * i);
        }
        Some(k)
    }

    #[test]
    fn short_vs_long_order() {
        let longs: Vec<[u8; 33]> = (0..400u64)
            .map(|i| {
                let x = (mix(i) as u128) << 64 | mix(i + 7) as u128;
                sample([b'e', b'k', b'u'][(i % 3) as usize], x)
            })
            .collect();
        let mut shorts: Vec<Vec<u8>> = Vec::new();
        for l in &longs {
            for n in 1..=10 {
                shorts.push(l[..n].to_vec()); // proper prefixes: equal head
                let mut s = l[..n].to_vec();
                let last = s[n - 1];
                for alt in [b'0', b'9', b'a', b'f', b'g', b'z', b'Z', b'_'] {
                    if alt != last {
                        s[n - 1] = alt;
                        shorts.push(s.clone());
                    }
                }
            }
        }
        for s in [&b"u"[..], b"u1", b"uzzzzzzzzz", b"k0", b"e", b"c_12", b"U9", b"v"] {
            shorts.push(s.to_vec());
        }
        for l in &longs {
            let (p, v) = parse(l).unwrap();
            assert_eq!(head_key(p, v), pack(&l[..10]).unwrap());
            for s in shorts.iter().step_by(3) {
                let ks = pack(s).unwrap();
                assert_eq!(cmp_short_long(ks, p, v), s.as_slice().cmp(l.as_slice()), "{:?}", s);
            }
        }
    }

    /// `cargo test --release hex32bench -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn hex32bench() {
        use std::hint::black_box;
        use std::time::Instant;
        const N: usize = 4096;
        let mut buf = Vec::with_capacity(N * 33);
        for i in 0..N as u64 {
            let x = (mix(i) as u128) << 64 | mix(!i) as u128;
            buf.extend_from_slice(&sample(b'u', x));
        }
        let ids: Vec<&[u8]> = buf.chunks(33).collect();
        let reps = 2000;
        let run = |name: &str, f: &dyn Fn(&[u8]) -> u128| {
            let t = Instant::now();
            let mut acc = 0u128;
            for _ in 0..reps {
                for id in &ids {
                    acc = acc.wrapping_add(f(black_box(id)));
                }
            }
            let ns = t.elapsed().as_nanos() as f64 / (reps * N) as f64;
            eprintln!("{name:<14} {ns:6.2} ns/call  (acc {:x})", acc as u16);
        };
        run("simd", &|b| parse(b).map_or(0, |x| x.1));
        run("simd_with", &|b| parse_with(b, b'u').unwrap_or(0));
        run("scalar", &|b| parse_scalar(b).map_or(0, |x| x.1));
        // reject path: uppercase at the last digit
        let mut bad = buf.clone();
        for c in bad.chunks_mut(33) {
            c[32] = b'A';
        }
        let bids: Vec<&[u8]> = bad.chunks(33).collect();
        let t = Instant::now();
        let mut n = 0usize;
        for _ in 0..reps {
            for id in &bids {
                n += parse(black_box(id)).is_none() as usize;
            }
        }
        let ns = t.elapsed().as_nanos() as f64 / (reps * N) as f64;
        eprintln!("{:<14} {ns:6.2} ns/call  ({n})", "simd reject");
    }
}
