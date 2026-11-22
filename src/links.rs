use std::cmp::Ordering;
use std::sync::atomic::Ordering::{AcqRel, Acquire, Relaxed};

use rayon::prelude::*;

use super::{Ids, Input, LinkTable, Scan, for_each_record};

impl LinkTable {
    #[inline(always)]
    fn intern(&self, key: u64) -> u32 {
        let mut s = self.slot(key);
        loop {
            let cell = unsafe { self.slots.get_unchecked(s) };
            let k = cell[0].load(Acquire);
            if k == key {
                return s as u32;
            }
            if k == 0 {
                match cell[0].compare_exchange(0, key, AcqRel, Acquire) {
                    Ok(_) => return s as u32,
                    Err(existing) if existing == key => return s as u32,
                    Err(_) => {}
                }
            }
            s = (s + 1) & self.mask;
        }
    }

    #[inline(always)]
    fn root(&self, mut i: u32) -> u32 {
        loop {
            let cell = unsafe { self.slots.get_unchecked(i as usize) };
            let p_raw = cell[1].load(Acquire) as u32;
            if p_raw == 0 || p_raw == i + 1 {
                return i;
            }
            let p = p_raw - 1;
            let gp_raw = unsafe { self.slots.get_unchecked(p as usize)[1].load(Acquire) as u32 };
            let gp = if gp_raw == 0 { p } else { gp_raw - 1 };
            if gp == p {
                return p;
            }
            let _ = cell[1].compare_exchange_weak(p_raw as u64, (gp + 1) as u64, AcqRel, Acquire);
            i = gp;
        }
    }

    #[inline(always)]
    fn union(&self, a: u32, b: u32, ids: &Ids<'_>) {
        loop {
            let (ra, rb) = (self.root(a), self.root(b));
            if ra == rb {
                return;
            }
            let ka = unsafe { self.slots.get_unchecked(ra as usize)[0].load(Acquire) };
            let kb = unsafe { self.slots.get_unchecked(rb as usize)[0].load(Acquire) };
            let (smaller, larger) = if ids.cmp(ka, kb) == Ordering::Less {
                (ra, rb)
            } else {
                (rb, ra)
            };
            let cell = unsafe { self.slots.get_unchecked(larger as usize) };
            let cur = cell[1].load(Acquire) as u32;
            if cur == 0 {
                if cell[1].compare_exchange(0, (smaller + 1) as u64, AcqRel, Acquire).is_ok() {
                    return;
                }
            } else if cur == larger + 1 {
                if cell[1].compare_exchange((larger + 1) as u64, (smaller + 1) as u64, AcqRel, Acquire).is_ok() {
                    return;
                }
            }
        }
    }
}

#[inline]
pub(super) fn decode_link<'a>(fields: &[&'a [u8]; 2], ids: &Ids<'a>) -> Option<(u64, u64)> {
    if fields[0].is_empty() || fields[1].is_empty() {
        return None;
    }
    Some((ids.key(fields[0]), ids.key(fields[1])))
}

pub(super) fn load_links<'a>(
    input: &'a Input,
    chunk: usize,
    scan: Scan,
    ids: &Ids<'a>,
    hmask: u64,
) -> (LinkTable, usize) {
    let in_bytes: usize = input.maps.iter().map(|m| m.len()).sum();
    let cap = if in_bytes < 1_048_576 {
        in_bytes.next_power_of_two().max(16)
    } else {
        (in_bytes / 9).next_power_of_two().max(16)
    };
    let table = LinkTable::new_with_cap(cap, hmask);

    input
        .chunks(chunk.min(256 << 10))
        .par_iter()
        .for_each(|&(fi, s, e)| {
            let buf: &'a [u8] = &input.maps[fi];
            #[cfg(any(target_arch = "aarch64", all(target_arch = "x86_64", target_feature = "ssse3")))]
            if scan == Scan::Simd && ids.simd_pack {
                super::columns::links_for_each(buf, s, e, ids, |(a, b)| {
                    let sa = table.intern(a);
                    let sb = table.intern(b);
                    table.union(sa, sb, ids);
                });
                return;
            }
            for_each_record(buf, s, e, scan, |fields| {
                if let Some((a, b)) = decode_link(fields, ids) {
                    let sa = table.intern(a);
                    let sb = table.intern(b);
                    table.union(sa, sb, ids);
                }
            });
        });

    // Pass 1: path compression so every node points directly to its root.
    table.slots
        .par_chunks(4096)
        .enumerate()
        .for_each(|(chunk_idx, chunk)| {
            for (offset, slot) in chunk.iter().enumerate() {
                if slot[0].load(Relaxed) != 0 {
                    let i = (chunk_idx * 4096 + offset) as u32;
                    let p_raw = slot[1].load(Relaxed) as u32;
                    if p_raw != 0 && p_raw != i + 1 {
                        let root = table.root(i);
                        slot[1].store((root + 1) as u64, Relaxed);
                    }
                }
            }
        });

    // Pass 2: resolve person and count distinct linked IDs.
    let linked: usize = table.slots
        .par_chunks(4096)
        .enumerate()
        .map(|(chunk_idx, chunk)| {
            let mut count = 0;
            for (offset, slot) in chunk.iter().enumerate() {
                let key = slot[0].load(Relaxed);
                if key != 0 {
                    count += 1;
                    let home = table.slot(key);
                    table.membership[home >> 6].fetch_or(1u64 << (home & 63), Relaxed);
                    let i = (chunk_idx * 4096 + offset) as u32;
                    let p_raw = slot[1].load(Relaxed) as u32;
                    let root = if p_raw == 0 || p_raw == i + 1 { i } else { p_raw - 1 };
                    let person = table.slots[root as usize][0].load(Relaxed);
                    slot[1].store(person, Relaxed);
                }
            }
            count
        })
        .sum();

    (table, linked)
}

#[cfg(test)]
mod tests {
    use super::*;
    use memmap2::MmapMut;
    use std::fmt::Write;

    #[test]
    fn linked_people_match_serial_union_across_workers() {
        // Alternate dense chains with separate components, duplicate/reversed
        // edges, and fallback IDs that sort before every packed ID.
        let names: Vec<_> = (0..3072)
            .map(|i| {
                if i % 17 == 0 {
                    format!("A long ID {i:04}")
                } else {
                    format!("u{i:04}")
                }
            })
            .collect();
        let mut edges = Vec::new();
        for i in 0..names.len() {
            if i + 3 < names.len() {
                edges.push((i, i + 3));
            }
            if i % 5 == 0 && i + 3 < names.len() {
                edges.push((i + 3, i));
                edges.push((i, i));
            }
        }
        // A shared device crosses two components. The third stays separate.
        edges.push((0, 1));
        edges.reverse();
        let mut csv = String::from("user_id_a,user_id_b\n");
        for &(a, b) in &edges {
            writeln!(&mut csv, "{},\"{}\"", names[a], names[b]).unwrap();
        }
        csv.push_str("bad,\nwrong,line,shape\n\"unterminated,x\n");
        let mut mapping = MmapMut::map_anon(csv.len()).unwrap();
        mapping.copy_from_slice(csv.as_bytes());
        let input = Input {
            maps: vec![mapping.make_read_only().unwrap()],
        };

        // v3's serial union and subsequent scan for the smallest ID.
        fn find(parents: &mut [usize], i: usize) -> usize {
            let mut root = i;
            while parents[root] != root {
                root = parents[root];
            }
            parents[i] = root;
            root
        }
        let mut parents: Vec<_> = (0..names.len()).collect();
        for (a, b) in edges {
            let (a, b) = (find(&mut parents, a), find(&mut parents, b));
            parents[b] = a;
        }
        let mut best = vec![None; names.len()];
        for (i, name) in names.iter().enumerate() {
            let root = find(&mut parents, i);
            best[root] = Some(best[root].map_or(name, |old: &String| old.min(name)));
        }
        for threads in [1, 2, 8] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            for no_fast in 0..=2 {
                let ids = Ids::new(no_fast);
                let (table, linked) =
                    pool.install(|| load_links(&input, 97, Scan::Scalar, &ids, u64::MAX));
                assert_eq!(linked, names.len());
                for (i, name) in names.iter().enumerate() {
                    let key = ids.key(name.as_bytes());
                    let actual = table.get_at(key, table.slot(key));
                    let root = find(&mut parents, i);
                    assert_eq!(actual, ids.key(best[root].unwrap().as_bytes()), "ID {name}");
                }
            }
        }
    }
}
