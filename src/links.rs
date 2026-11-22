use std::cmp::Ordering;
use std::sync::atomic::{
    AtomicU32, AtomicU64,
    Ordering::{AcqRel, Acquire, Relaxed},
};

use rayon::prelude::*;

use super::{Ids, Input, LinkTable, Scan, for_each_record, mix};

/// A hash slot is also the node index. The key stays immutable once published.
struct Components {
    keys: Vec<AtomicU64>,
    parents: Vec<AtomicU32>,
    mask: usize,
}

impl Components {
    fn new(edges: usize) -> Self {
        // At most two distinct IDs per edge, so the table stays at most 2/3 full.
        let cap = (3 * edges).next_power_of_two().max(16);
        assert!(u32::try_from(cap - 1).is_ok(), "too many link slots");
        let (keys, parents) = rayon::join(
            || vec_init(cap, |_| AtomicU64::new(0)),
            || vec_init(cap, |i| AtomicU32::new(i as u32)),
        );
        Self {
            keys,
            parents,
            mask: cap - 1,
        }
    }

    fn intern(&self, key: u64) -> u32 {
        let mut slot = mix(key) as usize & self.mask;
        loop {
            let cell = &self.keys[slot];
            match cell.load(Acquire) {
                existing if existing == key => return slot as u32,
                0 => match cell.compare_exchange(0, key, AcqRel, Acquire) {
                    Ok(_) => return slot as u32,
                    Err(existing) if existing == key => return slot as u32,
                    Err(_) => {}
                },
                _ => {}
            }
            slot = (slot + 1) & self.mask;
        }
    }

    fn root(&self, mut i: u32) -> u32 {
        loop {
            let cell = &self.parents[i as usize];
            let p = cell.load(Acquire);
            if p == i {
                return i;
            }
            let grandparent = self.parents[p as usize].load(Acquire);
            if grandparent == p {
                return p;
            }
            // Shorten a path only if the observed edge is still present.
            let _ = cell.compare_exchange_weak(p, grandparent, AcqRel, Acquire);
            i = grandparent;
        }
    }

    fn union(&self, a: u32, b: u32, ids: &Ids<'_>) {
        loop {
            let (ra, rb) = (self.root(a), self.root(b));
            if ra == rb {
                return;
            }
            let ka = self.keys[ra as usize].load(Acquire);
            let kb = self.keys[rb as usize].load(Acquire);
            let (smaller, larger) = if ids.cmp(ka, kb) == Ordering::Less {
                (ra, rb)
            } else {
                (rb, ra)
            };
            // Every edge points to a strictly smaller ID, so a concurrent move
            // of the smaller root cannot make a cycle. Retry if the larger
            // root moved. The remaining root is the component's smallest ID.
            if self.parents[larger as usize]
                .compare_exchange(larger, smaller, AcqRel, Acquire)
                .is_ok()
            {
                return;
            }
        }
    }
}

fn vec_init<T: Send>(cap: usize, f: impl Fn(usize) -> T + Send + Sync) -> Vec<T> {
    (0..cap).into_par_iter().with_min_len(4096).map(f).collect()
}

pub(super) fn load_links<'a>(
    input: &'a Input,
    chunk: usize,
    scan: Scan,
    ids: &Ids<'a>,
    hmask: u64,
) -> (LinkTable, usize) {
    let pairs: Vec<Vec<_>> = input
        .chunks(chunk.min(256 << 10))
        .par_iter()
        .map(|&(fi, s, e)| {
            let buf: &'a [u8] = &input.maps[fi];
            let mut pairs = Vec::new();
            for_each_record(buf, s, e, scan, |fields: &[&'a [u8]; 2]| {
                if !fields[0].is_empty() && !fields[1].is_empty() {
                    pairs.push((ids.key(fields[0]), ids.key(fields[1])));
                }
            });
            pairs
        })
        .collect();

    let components = Components::new(pairs.iter().map(Vec::len).sum());
    pairs.into_par_iter().for_each(|pairs| {
        for (a, b) in pairs {
            let (a, b) = (components.intern(a), components.intern(b));
            components.union(a, b, ids);
        }
    });

    let pieces: Vec<_> = components
        .keys
        .par_chunks(4096)
        .enumerate()
        .map(|(part, keys)| {
            let mut records = Vec::new();
            let mut linked = 0;
            for (offset, key) in keys.iter().enumerate() {
                let key = key.load(Relaxed);
                if key != 0 {
                    linked += 1;
                    let i = (part * 4096 + offset) as u32;
                    let root = components.root(i);
                    if i != root {
                        records.push((key, components.keys[root as usize].load(Relaxed)));
                    }
                }
            }
            (records, linked)
        })
        .collect();
    let linked = pieces.iter().map(|(_, n)| n).sum();
    let remapped = pieces.iter().map(|(records, _)| records.len()).sum();
    let table = LinkTable::new(remapped, hmask);
    pieces.into_par_iter().for_each(|(records, _)| {
        for (key, person) in records {
            table.insert(key, person);
        }
    });
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
