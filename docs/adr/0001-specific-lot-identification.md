# Specific-lot identification instead of weighted average cost

Every sell records which lots it draws from and how much from each (its allocations), and realized P&L is computed per allocation against that lot's own cost. We chose this over weighted-average cost because the user wants to decide which buy a sell closes, so P&L reflects that real choice; the price is a heavier sell flow (the user must allocate, helped by an editable FIFO pre-fill) and edit/delete rules that block any change leaving an allocation uncovered.

## Considered Options

- **Weighted average cost**: simplest sell flow and no lot bookkeeping, but cannot answer "what did I make on *that* buy". Kept only as the informational Average Buy Price.
- **Automatic FIFO**: no user input on sells, but takes the choice away from the user. Kept only as the UI pre-fill suggestion; the backend never chooses lots.

## Consequences

- Allocations are stored records; positions, cost basis and P&L are derived from them (see ADR-0002).
- Editing or deleting a lot is blocked while it would leave an existing allocation uncovered (quantity too low, or lot date after the sell date). Sells are never silently re-allocated.
- Switching back to average cost later would mean discarding allocation data, so this is hard to reverse.
