//! Who holds the submission lock (the host's `submitted`) and for how long.
//!
//! Every place that takes the lock takes it through [`take`] and names
//! itself. In tests each place's waits and holds are counted, and a wait
//! is put down to the place that held the lock when the wait began. In a
//! build nothing is counted: the guard is the lock's own.
//!
//! The bench below (`lock_census`) runs the shape of fork #1375 on the
//! relay: a submitting thread sends flights while recording threads make
//! lists and title threads block on fences, which settle under the lock.

use std::sync::{Mutex, MutexGuard};

/// [`super::Host::submit`]: preparing and sending a submission, and what its
/// caller does before letting go (a wait for fewer lists in the air).
pub(super) const SUBMIT: usize = 0;
/// [`super::settle_now`] for a present, a sweep or a step of ours.
pub(super) const SETTLE_SYNC: usize = 1;
/// [`super::settle_now`] for a fence the title blocks on.
pub(super) const SETTLE_FENCE: usize = 2;
/// [`super::settle_now`] for a memory value the title waits for.
pub(super) const SETTLE_VALUE: usize = 3;
/// The thread that settles once the card has run everything (no relay).
pub(super) const HELPER: usize = 4;
#[cfg(test)]
const PLACES: usize = 5;
#[cfg(test)]
const NAMES: [&str; PLACES] = [
    "submit",
    "settle_now (sync)",
    "settle_now (fence)",
    "settle_now (value)",
    "late helper",
];

/// The place of [`super::settle_now`] for its reason.
pub(super) fn settle_place(why: usize) -> usize {
    match why {
        super::WHY_FENCE => SETTLE_FENCE,
        super::WHY_VALUE => SETTLE_VALUE,
        _ => SETTLE_SYNC,
    }
}

/// The submission lock, held: the last value signalled on the host's fence.
pub(super) struct Held<'a> {
    guard: MutexGuard<'a, u64>,
    #[cfg(test)]
    taken: (usize, std::time::Instant),
}

impl std::ops::Deref for Held<'_> {
    type Target = u64;
    fn deref(&self) -> &u64 {
        &self.guard
    }
}

impl std::ops::DerefMut for Held<'_> {
    fn deref_mut(&mut self) -> &mut u64 {
        &mut self.guard
    }
}

/// Takes the submission lock for `place` (one of the constants above).
#[cfg_attr(not(test), allow(unused_variables))]
pub(super) fn take(lock: &Mutex<u64>, place: usize) -> Held<'_> {
    #[cfg(test)]
    let (asked, behind) = (
        std::time::Instant::now(),
        count::HOLDER.load(std::sync::atomic::Ordering::Relaxed),
    );
    let guard = lock.lock().unwrap_or_else(|e| e.into_inner());
    #[cfg(test)]
    {
        let now = std::time::Instant::now();
        count::waited(place, behind, (now - asked).as_nanos() as u64);
        Held {
            guard,
            taken: (place, now),
        }
    }
    #[cfg(not(test))]
    Held { guard }
}

#[cfg(test)]
impl Drop for Held<'_> {
    fn drop(&mut self) {
        // Still held: the guard goes after this.
        count::held(self.taken.0, self.taken.1.elapsed().as_nanos() as u64);
    }
}

#[cfg(test)]
pub(super) mod count {
    use super::{NAMES, PLACES};
    use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};

    /// The place holding the lock, plus one; 0 when free.
    pub(super) static HOLDER: AtomicUsize = AtomicUsize::new(0);
    /// Per place: times taken, ns waited, ns held, longest hold in ns.
    static TAKEN: [[AtomicU64; 4]; PLACES] = [const { [const { AtomicU64::new(0) }; 4] }; PLACES];
    /// ns a place waited, by who held the lock when it began (0: nobody).
    static BEHIND: [[AtomicU64; PLACES + 1]; PLACES] =
        [const { [const { AtomicU64::new(0) }; PLACES + 1] }; PLACES];

    pub(super) fn waited(place: usize, behind: usize, ns: u64) {
        TAKEN[place][1].fetch_add(ns, Ordering::Relaxed);
        BEHIND[place][behind].fetch_add(ns, Ordering::Relaxed);
        HOLDER.store(place + 1, Ordering::Relaxed);
    }

    pub(super) fn held(place: usize, ns: u64) {
        HOLDER.store(0, Ordering::Relaxed);
        TAKEN[place][0].fetch_add(1, Ordering::Relaxed);
        TAKEN[place][2].fetch_add(ns, Ordering::Relaxed);
        TAKEN[place][3].fetch_max(ns, Ordering::Relaxed);
    }

    /// What was counted since the last call, per place: times taken, ms
    /// waited, ms held, longest hold in ms, and ms waited behind each place
    /// (first: behind nobody).
    pub(crate) fn take() -> Vec<(u64, f64, f64, f64, Vec<f64>)> {
        let ms = |a: &AtomicU64| a.swap(0, Ordering::Relaxed) as f64 / 1e6;
        (0..PLACES)
            .map(|p| {
                let t = &TAKEN[p];
                (
                    t[0].swap(0, Ordering::Relaxed),
                    ms(&t[1]),
                    ms(&t[2]),
                    ms(&t[3]),
                    BEHIND[p].iter().map(ms).collect(),
                )
            })
            .collect()
    }

    pub(crate) fn name(place: usize) -> &'static str {
        NAMES[place]
    }
}

#[cfg(test)]
mod bench;
