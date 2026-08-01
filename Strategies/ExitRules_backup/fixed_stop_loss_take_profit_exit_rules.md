# Exit Strategy Rules

## Strategy Metadata

Exit Strategy Name: Fixed Stop-Loss / Take-Profit
Applies To: Any trade opened by the backtester
Timeframe: Daily (closing price only, no intraday)

---

## Entry Reference

Entry Price: Opening price on the trading day immediately after the signal day.

---

## Exit Conditions

Check ONCE PER DAY, using that day's closing price. Exit as soon as ANY
condition below is true.

### Condition 1: Stop-Loss

Close <= EntryPrice * (1 - StopLossPct / 100)

StopLossPct = 5

Reason Tag: "SL"

---

### Condition 2: Take-Profit

Close >= EntryPrice * (1 + TakeProfitPct / 100)

TakeProfitPct = 10

Reason Tag: "TP"

---

## Fallback

If no condition above triggers before the available data ends, do not exit -
the backtester itself force-closes any still-open trade at the last
available close, tagged "RangeEnd". Exit strategies never need to implement
this fallback themselves.
