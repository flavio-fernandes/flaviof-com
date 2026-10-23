import gzip, csv, datetime as dt, collections
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch

SURFACE = "#fcfcfb"
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
BEFORE, AFTER = "#2a78d6", "#eb6834"
CUT = dt.date(2026, 8, 2)          # pre-migration ends 2026-08-01 23:00 EDT

rows = []
with gzip.open("/root/viz/home-lux.csv.gz", "rt") as f:
    for r in csv.DictReader(f):
        rows.append((dt.datetime.fromtimestamp(int(r["created_epoch"]),
                                               dt.timezone.utc), int(r["value"])))

def pct(s, p):
    s = sorted(s)
    return s[max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))]

days = collections.defaultdict(list)
for t, v in rows:
    days[t.date()].append(v)
ds = sorted(days)

fig, ax = plt.subplots(figsize=(10, 4.6), dpi=160)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)

for d in ds:
    lo, hi = pct(days[d], 5), pct(days[d], 95)
    ax.bar(d, hi - lo, bottom=lo, width=0.78,
           color=AFTER if d >= CUT else BEFORE, lw=0)

# 10-bit rail
ax.axhline(1023, color=MUTED, lw=1.0, ls=(0, (2, 3)))
ax.annotate("10-bit rail 1023", xy=(1.0, 1023), xycoords=("axes fraction", "data"),
            xytext=(7, 0), textcoords="offset points", color=INK_2,
            fontsize=8.5, ha="left", va="center", annotation_clip=False)

# Thresholds, recessive ink with direct labels in the right margin.
for y, lab in ((600, "new high-water 600"), (460, "new low-water 460"),
               (360, "old low-water 360")):
    ax.axhline(y, color=MUTED, lw=1.0, ls=(0, (5, 4)), zorder=4)
    ax.annotate(lab, xy=(1.0, y), xycoords=("axes fraction", "data"),
                xytext=(7, 0), textcoords="offset points", color=INK_2,
                fontsize=8.5, ha="left", va="center", annotation_clip=False)

ax.annotate("the bright end jumps to the rail",
            xy=(dt.date(2026, 8, 2), 1000), xytext=(-14, -30),
            textcoords="offset points", color=AFTER, fontsize=9.5,
            fontweight="bold", ha="right", va="top",
            arrowprops=dict(arrowstyle="-", color=AFTER, lw=1.2))
ax.annotate("the dark end does not move",
            xy=(dt.date(2026, 7, 6), 155), xytext=(0, -30),
            textcoords="offset points", color=INK_2, fontsize=9.5,
            fontweight="bold", ha="center", va="top",
            arrowprops=dict(arrowstyle="-", color=INK_2, lw=1.0))

ax.set_ylim(0, 1120)
ax.set_xlim(ds[0] - dt.timedelta(days=1), ds[-1] + dt.timedelta(days=1))
ax.set_ylabel("light value (10-sample average)", color=INK_2, fontsize=9.5)
ax.set_title("Sixty days of the value the dimming logic actually compares",
             color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=10)

ax.legend(handles=[Patch(color=BEFORE, label="original software"),
                   Patch(color=AFTER, label="new software")],
          loc="upper left", frameon=False, fontsize=9,
          bbox_to_anchor=(0.005, 0.99))

ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
ax.grid(axis="y", color=GRID, lw=0.8)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
for s in ("left", "bottom"):
    ax.spines[s].set_color("#d8d7d2")
ax.tick_params(colors=INK_2, labelsize=8.5, length=0)

fig.subplots_adjust(left=0.075, right=0.83, top=0.87, bottom=0.09)
fig.savefig("/root/viz/out2.png", facecolor=SURFACE)
print("ok  bars:", len(ds))
