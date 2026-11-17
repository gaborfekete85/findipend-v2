# Findipend

Findipend tracks a user's cryptocurrency holdings across portfolios, recording buys and sells and reporting cost basis and profit/loss in USD.

## Language

### People and containers

**User**:
A signed-in person who owns portfolios; nothing is shared between users.
_Avoid_: Account, customer, owner

**Portfolio**:
A named collection of one user's lots and sells (e.g. "Altcoins", "DeFi").
_Avoid_: Wallet, account

**Asset**:
A cryptocurrency identified by its CoinGecko id.
_Avoid_: Coin, token, ticker

### Trades

**Buy**:
A transaction acquiring a quantity of an asset for a total USD amount, fee included, on a given date. Every buy opens exactly one lot.
_Avoid_: Purchase, entry

**Lot**:
The holding created by a single buy: its quantity, its total cost, and how much of it remains unsold.
_Avoid_: Buy position, tranche, position (when meaning a single buy)

**Sell**:
A transaction disposing of a quantity of an asset for a total USD amount received, fee included, drawn from one or more lots chosen by the user.
_Avoid_: Sale, exit

**Allocation**:
The part of a sell drawn from one specific lot: a quantity, plus that quantity's pro-rata share of the sell's proceeds and fee.
_Avoid_: Match, lot link, split

**Fee**:
The trading cost of a buy or sell, contained within its total amount (not added on top); defaults to 0.1% of the total and may be overridden.
_Avoid_: Commission

**Trade Date**:
The calendar date (no time) the user says a buy or sell happened; defaults to today.
_Avoid_: Created at, entry date

### Analytics

**Position**:
The aggregate of all open lots of one asset in a portfolio; always derived, never stored.
_Avoid_: Holding (when meaning a single lot)

**Closed Position**:
An asset in a portfolio whose lots are all fully sold; kept visible for its realized P&L.
_Avoid_: Exited position, archived asset

**Cost Basis**:
The remaining USD cost of open lots: each lot's cost per unit times its unsold quantity. The base for unrealized P&L.
_Avoid_: Invested amount, book value

**Total Invested**:
All USD ever paid into buys, regardless of later sells. Informational only; never used to compute P&L.
_Avoid_: Cost basis, capital

**Average Buy Price**:
A position's cost basis divided by its unsold quantity. Informational only.
_Avoid_: Weighted average cost (as a cost method), entry price

**Realized P&L**:
Profit or loss locked in by sells: the sum over allocations of allocated proceeds minus the allocated lot cost.
_Avoid_: Realized profit, gains

**Unrealized P&L**:
Current market value of open holdings minus their cost basis.
_Avoid_: Paper profit, floating P&L
