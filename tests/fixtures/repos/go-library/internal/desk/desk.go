package desk

import (
	_ "embed"
	"fmt"

	rules "example.com/library/internal/policy"
)

const (
	Available = iota
	OnLoan
	Overdue
)

var lateDays, maxFine = 14, 500

//go:embed ledger.go
var ledgerSource string

// Desk lends items to patrons and keeps the ledger of what is out.
type Desk struct {
	loans   int
	entries []string
}

// Stack is a last-in, first-out list.
type Stack[T any] struct {
	items []T
}

// Push puts an item on top of the stack.
func (s *Stack[T]) Push(item T) {
	s.items = append(s.items, item)
}

// CheckOut lends an item to a patron and posts the loan.
func (d *Desk) CheckOut(patron, item string) error {
	if item == "" {
		return fmt.Errorf("no item for %s", patron)
	}
	d.loans++
	fine := rules.LateFee(lateDays)
	d.entries = postEntry(d.entries, fmt.Sprintf("%s %s %d", patron, item, fine))
	return nil
}
