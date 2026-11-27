pub fn clamp(value: u32, low: u32, high: u32) -> u32 {
    value.max(low).min(high)
}
