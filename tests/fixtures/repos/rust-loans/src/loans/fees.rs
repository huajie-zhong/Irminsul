use super::policy;
use crate::loans::policy::{due_day, LIMIT as CAP};
use crate::util::{self, clamp};

const RATE: u32 = 50;
static GRACE: u32 = 3;

macro_rules! weeks {
    ($count:expr) => {
        $count * 7
    };
}

/// The fee, in cents, for a payment on day `paid` of a loan entered on day `entered`.
pub fn late_fee(entered: u32, paid: u32) -> u32 {
    let late = paid.saturating_sub(due_day(entered));
    util::clamp(late * RATE, 0, CAP)
}

/// The day a loan entered on day `entered` may come back without a fee.
pub fn grace_day(entered: u32) -> u32 {
    fn round_up(day: u32) -> u32 {
        (day + 6) / 7 * 7
    }

    round_up(policy::due_day(entered)) + weeks!(GRACE)
}

/// A desk that lends items and keeps its own day.
#[derive(Debug, Clone)]
// Read by the shelf code, which lives outside this crate.
#[allow(dead_code)]
pub struct Desk {
    pub name: String,
    pub day: u32,
}

pub enum Fee {
    Waived,
    Charged(u32),
}

pub trait Opener {
    fn open(&self) -> bool;

    fn is_open(&self) -> bool {
        self.open()
    }
}

impl Desk {
    pub fn new() -> Self {
        Desk {
            name: String::new(),
            day: 0,
        }
    }

    #[inline]
    pub fn open_days(&self) -> u32 {
        clamp(self.day, 0, 365)
    }
}

impl Opener for Desk {
    fn open(&self) -> bool {
        self.day > 0
    }
}

pub struct Stack<T>(Vec<T>);

impl<T> Opener for Stack<T> {
    fn open(&self) -> bool {
        !self.0.is_empty()
    }
}

impl Opener for &Desk {
    fn open(&self) -> bool {
        self.day > 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn late_fee() {
        assert!(matches!(charged(), Fee::Charged(450)));
        assert_eq!(super::late_fee(1, 33), 100);
    }

    #[tokio::test]
    async fn fee_is_waived_on_time() {
        assert_eq!(super::late_fee(1, 31), 0);
    }

    fn charged() -> Fee {
        Fee::Charged(super::late_fee(1, 40))
    }
}
