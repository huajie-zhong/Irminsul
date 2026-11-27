package desk

import "testing"

func TestCheckOut(t *testing.T) {
	d := newDesk()
	if err := d.CheckOut("ada", "book-1"); err != nil {
		t.Fatal(err)
	}
	if !Testable(d) {
		t.Errorf("CheckOut left %d loans, want 1", d.loans)
	}
}

func Testable(d *Desk) bool {
	return d.loans == 1
}

func newDesk() *Desk {
	return &Desk{}
}
