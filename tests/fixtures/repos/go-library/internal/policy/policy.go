// Package policy prices a loan that comes back late.
package policy

// Rule prices one late loan.
type Rule interface {
	Fee(days int) int
}

// LateFee is the fine for a loan returned days after it fell due.
func LateFee(days int) int {
	if days <= 0 {
		return 0
	}
	return days * 25
}
