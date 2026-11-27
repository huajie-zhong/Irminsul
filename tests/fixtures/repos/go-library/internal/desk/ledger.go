package desk

// postEntry adds one line to the ledger and returns the ledger.
func postEntry(entries []string, line string) []string {
	type entry struct {
		text string
	}
	posted := entry{text: line}
	return append(entries, posted.text)
}
