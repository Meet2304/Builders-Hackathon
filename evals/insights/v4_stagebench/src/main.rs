mod scan;
mod dec;
use std::hint::black_box;
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let buf = std::fs::read(&a[1]).unwrap();
    let mode: u32 = a[2].parse().unwrap();
    let start = memchr::memchr(b'\n', &buf).unwrap() + 1;
    let end = buf.len();
    let mut acc = 0usize;
    let mut n = 0usize;
    match mode {
        0 => {} // load only
        1 => scan::v3::for_each_line(&buf, start, end, |l| { n += 1; acc += l.len(); }),
        2 => scan::v3::for_each_line(&buf, start, end, |l| { let mut o = [&[][..]; 7]; n += 1; if scan::v3::split_fields(l, &mut o) { acc += o[5].len(); } }),
        3 => scan::v3::for_each_record::<7>(&buf, start, end, scan::v3::Scan::Simd, |f| { n += 1; acc += f[5].len(); }),
        4 => scan::v4::for_each_record::<7>(&buf, start, end, scan::v4::Scan::Simd, |f| { n += 1; acc += f[5].len(); }),
        5 => scan::v3::for_each_record::<7>(&buf, start, end, scan::v3::Scan::Swar, |f| { n += 1; acc += f[5].len(); }),
        6 => scan::v4::for_each_record::<7>(&buf, start, end, scan::v4::Scan::Swar, |f| { n += 1; acc += f[5].len(); }),
        7..=10 => {
            let w0 = dec::parse_ts(b"2028-01-23T00:00:00Z").unwrap(); let w1 = w0 + 14 * dec::DAY_MS;
            let d = dec::TimestampDecoder::new(w0, w1);
            let mut prod = dec::IdIndex::new(b"p", true);
            let names: Vec<Vec<u8>> = (0..50_000).map(|i| format!("p{i}").into_bytes()).collect();
            let leaked: &'static Vec<Vec<u8>> = Box::leak(Box::new(names));
            for (i, nm) in leaked.iter().enumerate() { prod.set(nm, (i % 20) as u32); }
            scan::v4::for_each_record::<7>(&buf, start, end, scan::v4::Scan::Simd, |f| {
                n += 1;
                let e = dec::pack(f[0]).unwrap_or(1); let u = dec::pack(f[1]).unwrap_or(1);
                acc = acc.wrapping_add((e ^ u) as usize);
                if mode >= 8 { let a = d.parse(f[2]).unwrap_or(0); let b = d.parse(f[3]).unwrap_or(0); acc = acc.wrapping_add((a ^ b) as usize); }
                if mode >= 9 { let p = match f[4] { b"view" | b"cart" => Some(0), b"purchase" => dec::parse_price(f[6]), _ => None }; acc = acc.wrapping_add(p.unwrap_or(7) as usize); }
                if mode >= 10 { acc = acc.wrapping_add(prod.get(f[5]).unwrap_or(99) as usize); }
            });
        }
        _ => {}
    }
    black_box(acc);
    eprintln!("mode {mode} records {n} acc {acc}");
}
