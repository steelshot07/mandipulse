# Key findings

From `notebooks/eda.py` over 1 Jan 2019 – 26 Nov 2026: 44,430 daily price reports → 6,923
market-weeks across 17 series, plus IMD gridded rainfall around each mandi. Weekly price =
median of the week's non-outlier daily modal prices (₹/quintal). Seasonal statistics use the
complete years 2019–2025. Refresh these numbers manually each release (PRD §5).

## 1. Onion and tomato prices swing about 3× within a typical year

Average price by month, relative to that year's average (1.00), across markets, 2019–2025:

| | Lowest month | Highest month | Peak ÷ trough |
|---|---|---|---|
| Onion | April (0.52) | November (1.56) | **3.0×** |
| Tomato | March (0.54) | July (1.59) | **3.0×** |
| Potato | February (0.63) | November (1.30) | 2.1× |

The onion pattern follows the crop calendar: the rabi harvest floods the market in March–May,
and stored stock runs down before the kharif crop in October–November. But the timing isn't
reliable. Only **58%** of onion market-years actually peaked in September–December (tomato
50%, potato 71%), so shocks often outweigh the calendar. That's why forecasts need more than
a seasonal-naive baseline.

## 2. Tomato is the most volatile week to week; potato is the calmest

| | Avg. abs. weekly change (last 52 wks, median market) | Weeks with a >25% move | CV of weekly price (last 52 wks) |
|---|---|---|---|
| Tomato | 16.6% | **20.8%** | 0.39 |
| Onion | 11.0% | 13.0% | **0.58** |
| Potato | 5.3% | 2.7% | 0.22 |

- Onion has the highest CV because of its large seasonal swing (finding 1). Tomato moves the
  most from one week to the next.
- The largest 4-week surge in the data is **Azadpur tomato: about 10× in the four weeks to
  3 Jul 2023**, reaching ₹6,531/quintal. This was the nationwide tomato price spike of
  mid-2023, and a similar jump (8.5×) happened in late June 2020.
- Practical implication: 1-week-ahead tomato forecasts will have wide uncertainty bands, and
  potato should be the easiest commodity to beat the baseline on.

## 3. Markets in the Nashik onion belt move as one; potato markets barely move together

Median correlation of weekly % price changes between pairs of markets:

- Onion overall: **r = 0.67**. Within the 7 Nashik-district markets it's **r = 0.80**; Nashik
  vs Bengaluru is 0.56.
- Tomato: 0.60.
- Potato: only **0.25** (Agra, Delhi and Kolkata draw on different supply chains).

Implications for Phase 4:
- One global onion model with market as a feature should work well; the Nashik markets are
  close to a single price signal.
- Potato markets need their own lags and dynamics.
- "Best mandi" comparisons inside the Nashik belt will usually show small differences.

## 4. Above-normal rain in the Nashik belt is followed by higher onion prices 3–5 weeks later

We correlated *rainfall over 4 weeks minus the 1991–2020 normal* (within about 55 km of the
mandi) with the *4-week price change* that follows, at lags of 0–12 weeks:

- All **7 Nashik-belt onion markets** peak at a **4-week lag, r = 0.22–0.30** (n ≈ 400 weeks
  each; |r| > 0.10 is significant at about 95%).
- Part of this is seasonal, since big rain anomalies and the seasonal price climb both happen
  in the monsoon. After removing each week-of-year's normal price change, **r = 0.11–0.21**
  remains, and it's strongest in June–October.
- Across all series, 64 of 221 (series, lag) pairs are significant, against about 11 expected
  by chance. These are almost all onion pairs.
- **There's no comparable effect for tomato, potato, Bengaluru or Mandsaur** (|r| < 0.15 at
  every lag).

This is a correlation, not proof of cause. It is consistent with excess rain damaging the
standing kharif crop and stored onion. Phase 4 should include rainfall-deviation lags of 3–5
weeks as features for onion, and the "why" panel can cite them when they matter. For
terminal markets (Azadpur, Kolkata, Bengaluru), local rain isn't where supply comes from, so
no effect is expected there.

## 5. Data quality: 6.5% of weeks are gaps, concentrated in two series

- **447 of 6,923 market-weeks** have no report. The 2-week carry-forward fills 190 of them,
  leaving 257 unfilled.
- **Madanapalle tomato** accounts for 167 unfilled weeks. It has a **120-week hole between
  2019 and 2022**, and reliable data only from 2023. Phase 4 should train on it from 2023 only.
- **Bengaluru onion** has a 35-week hole during the 2025 rename from Bangalore to Bengaluru.
- The outlier rule flags 95 reports (0.2%). Most are **Mandsaur** reports with a modal price
  of ₹100, which look like placeholders. Some slip through when the trailing median is itself
  low, which inflates Mandsaur's apparent volatility (27.7% average weekly change, against
  about 11% for other onion markets). Treat Mandsaur's volatility numbers with caution; a
  stricter, market-specific floor is a candidate fix.
