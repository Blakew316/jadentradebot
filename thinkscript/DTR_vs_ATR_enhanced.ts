# DTR vs ATR — Enhanced
# Based on "Custom ATR Plot" by 7of9 for BRT (usethinkscript.com thread #387).
# Enhancements: range-remaining label, ATR target lines from today's extremes,
# and an optional alert when the day's range exhausts the average.

declare upper;

input AtrAvgLength = 14;
input ShowTargets = yes;
input AlertOnExhaustion = no;

def dHigh  = high(period = aggregationPeriod.DAY);
def dLow   = low(period = aggregationPeriod.DAY);
def dClose = close(period = aggregationPeriod.DAY);

def ATR = WildersAverage(TrueRange(dHigh, dClose, dLow), AtrAvgLength);

def TodayHigh = Highest(dHigh, 1);
def TodayLow  = Lowest(dLow, 1);

def DTR = TodayHigh - TodayLow;
def DTRpct = Round((DTR / ATR) * 100, 0);
def RangeLeft = Max(ATR - DTR, 0);

# Original label
AddLabel(yes,
    "DTR " + Round(DTR, 2) + " vs ATR " + Round(ATR, 2) + "  " + Round(DTRpct, 0) + "%",
    (if DTRpct <= 70 then Color.GREEN
     else if DTRpct >= 90 then Color.RED
     else Color.ORANGE));

# Enhancement: dollars (and %) of the average daily range still unused
AddLabel(yes,
    "Range left $" + Round(RangeLeft, 2) + " (" + Round(Max(100 - DTRpct, 0), 0) + "%)",
    (if DTRpct <= 70 then Color.GREEN
     else if DTRpct >= 90 then Color.RED
     else Color.ORANGE));

# Enhancement: ATR-projected targets off today's extremes
plot UpTarget = if ShowTargets then TodayLow + ATR else Double.NaN;
UpTarget.SetDefaultColor(Color.GREEN);
UpTarget.SetPaintingStrategy(PaintingStrategy.DASHES);

plot DownTarget = if ShowTargets then TodayHigh - ATR else Double.NaN;
DownTarget.SetDefaultColor(Color.RED);
DownTarget.SetPaintingStrategy(PaintingStrategy.DASHES);

# Enhancement: alert once the average range is exhausted
Alert(AlertOnExhaustion and DTRpct >= 90, "Daily range exhausted (DTR >= 90% of ATR)", Alert.BAR, Sound.Ring);
