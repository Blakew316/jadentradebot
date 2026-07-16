# Custom ATR Plot by 7of9 for BRT
# edited 3/20/19
# Source: https://usethinkscript.com/threads/dtr-vs-atr-indicator-for-thinkorswim.387/
# Kept verbatim as the reference the Python port (jadentradebot) is tested against.

declare upper;

input AtrAvgLength = 14;

def ATR = WildersAverage(TrueRange(high(period = aggregationPeriod.DAY), close(period = aggregationPeriod.DAY), low(period = aggregationPeriod.DAY)), AtrAvgLength);

def TodayHigh = Highest(high(period = aggregationPeriod.DAY), 1);
def TodayLow = Lowest(low(period = aggregationPeriod.DAY), 1);

def DTR = TodayHigh - TodayLow;

def DTRpct = Round((DTR / ATR) * 100, 0);

AddLabel (yes, "DTR " + Round (DTR , 2) + " vs ATR " + round (ATR,2)+ "  " + round (DTRpct,0) + "%", (if DTRpct <= 70 then Color.GREEN else if DTRpct >= 90 then Color.RED else Color.ORANGE));
