# DTR vs ATR — Scanner / Watchlist column version
# Based on "Custom ATR Plot" by 7of9 for BRT (usethinkscript.com thread #387).
#
# AS A SCAN (Scan -> Stock Hacker -> Study filter, aggregation = 1 day):
#   paste the script and keep exactly one `plot scan = ...` line uncommented.
#
# AS A WATCHLIST COLUMN (custom column, aggregation = 1 day):
#   use the AddLabel/plot block at the bottom instead.

input AtrAvgLength = 14;

def ATR = WildersAverage(TrueRange(high, close, low), AtrAvgLength);
def DTR = high - low;
def DTRpct = Round((DTR / ATR) * 100, 0);

# --- pick ONE for scanning ---
plot scan = DTRpct <= 70;        # GREEN: still has room to move
# plot scan = DTRpct >= 90;      # RED: range exhausted
# plot scan = DTRpct > 70 and DTRpct < 90;   # ORANGE: extended

# --- watchlist column version (comment the plot above, uncomment below) ---
# AddLabel(yes, Round(DTRpct, 0) + "%",
#     (if DTRpct <= 70 then Color.GREEN
#      else if DTRpct >= 90 then Color.RED
#      else Color.ORANGE));
