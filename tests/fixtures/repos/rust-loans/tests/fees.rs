use rust_loans::loans::fees::late_fee;

#[test]
fn fee_is_capped() {
    assert_eq!(late_fee(1, 1000), cap());
}

fn cap() -> u32 {
    500
}
