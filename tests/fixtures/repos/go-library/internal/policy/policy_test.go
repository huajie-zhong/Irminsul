package policy_test

import (
	"testing"

	"example.com/library/internal/policy"
)

func TestLateFee(t *testing.T) {
	expect(t, "LateFee(3)", policy.LateFee(3), 75)
	expect(t, "LateFee(0)", policy.LateFee(0), 0)
}

func expect(t *testing.T, what string, got, want int) {
	t.Helper()
	if got != want {
		t.Errorf("%s = %d, want %d", what, got, want)
	}
}
