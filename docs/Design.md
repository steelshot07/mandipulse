# Design — MandiPulse

## 1. Principles

- **Mobile-first.** Many users will open it on a budget Android phone. Design at 375 px, then scale up.
- **Numbers first.** The current price, the forecast, and the signal should be readable in 2 seconds.
- **Honest uncertainty.** Always show the forecast band, never just a single line. Always show "Last updated".
- **Calm, not alarming.** A price rise is good news for a farmer and bad news for a buyer, so don't paint rises green and falls red. Use neutral direction colours and labels.
- **Light by default**, dark mode supported via Tailwind `dark:` classes.

## 2. Colour palette

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#FAFAF7` | `#121412` | Page background |
| `surface` | `#FFFFFF` | `#1C1F1C` | Cards |
| `border` | `#E5E5E0` | `#2E322E` | Card borders, dividers |
| `text` | `#1A1C1A` | `#ECEDEA` | Primary text |
| `text-muted` | `#5F635E` | `#A3A8A2` | Labels, captions |
| `primary` | `#2F6B4F` | `#5FAE86` | Brand, buttons, links, active nav |
| `primary-soft` | `#E4EFE8` | `#23382C` | Selected chips, highlights |
| `series-actual` | `#2F6B4F` | `#5FAE86` | Actual price line |
| `series-forecast` | `#3B6EA8` | `#7AA7DB` | Forecast line (dashed) |
| `band` | `#3B6EA8` @ 15% | `#7AA7DB` @ 20% | P10–P90 band |
| `baseline` | `#9A9A93` | `#7C807B` | Seasonal-naive line (dotted) |
| `signal-rising` | `#B26B00` | `#E0A040` | Rising badge (amber) |
| `signal-falling` | `#5B5FA8` | `#9A9EE0` | Falling badge (indigo) |
| `signal-stable` | `#5F635E` | `#A3A8A2` | Stable badge (grey) |
| `warning` | `#B26B00` | `#E0A040` | Stale data banner |
| `error` | `#B3261E` | `#F2B8B5` | Errors only |

Multi-mandi compare chart (max 4 series): `#2F6B4F`, `#3B6EA8`, `#B26B00`, `#8E4E8C`. Always pair colour with a legend label, never colour alone.

All text/background pairs must meet WCAG AA contrast (4.5:1 for body text).

## 3. Typography

- **Headings:** Plus Jakarta Sans (fallback: DM Sans, system-ui).
- **Body / UI text:** Inter (fallback: system-ui, sans-serif).
- **Prices, dates, table numbers:** Inter with `font-variant-numeric: tabular-nums` by default. Optional "market terminal" look: IBM Plex Mono for hero prices and table number columns only, never for body text. Decide once and apply everywhere via a `.num` utility class.
- **Hindi (later):** Noto Sans Devanagari as a fallback in every font stack (Plus Jakarta Sans and Plex Mono have no Devanagari); leave room for ~30% longer labels.
- Load at most 2 font families + weights 400/500/600/700, with `font-display: swap`, to keep mobile load fast.

| Role | Size / line height | Weight |
|---|---|---|
| Display (hero price) | 32 / 40 | 700 |
| H1 page title | 24 / 32 | 600 |
| H2 section | 18 / 26 | 600 |
| Body | 15 / 22 | 400 |
| Label / caption | 13 / 18 | 500 |
| Tiny (chart axis) | 12 / 16 | 400 |

## 4. Number & date formatting

- Currency: Indian grouping with rupee sign, e.g. `₹1,23,450`; unit shown once: `₹2,340 /quintal`.
- Percent change: `+12.4%` / `−8.1%` (use real minus sign), 1 decimal.
- Dates: `24 Nov 2026`; weeks: `Week of 23 Nov`.
- "Last updated" as relative + absolute: `2 days ago (24 Nov 2026)`.

## 5. Spacing, shape, elevation

- 4 px spacing scale (Tailwind default). Card padding 16 px mobile, 24 px desktop.
- Corner radius: cards 12 px, buttons/chips 8 px.
- Elevation: 1 px border + very soft shadow (`shadow-sm`). No heavy shadows.
- Max content width 1200 px.

## 6. Layout & navigation

Global commodity + market selector persists across pages via URL query params (`?commodity=onion&market=lasalgaon`), so links are shareable.

### 6.1 Mobile (375 px) — primary farmer view
Goal: answer "sell now or wait?" without horizontal scrolling or menus. Single column, top to bottom:

1. **Sticky top bar:** MandiPulse mark · Commodity pill ▾ · Mandi pill ▾ (tap targets ≥ 44 px).
2. **StaleBanner** (only when the series is > 7 days old, amber `warning`). Show *either* the stale banner *or* the normal "Updated …" line, never both with conflicting dates.
3. **Hero PriceCard:** `LASALGAON · ONION`, `₹2,340 /quintal` (display size), `+12.4% vs last week`, SignalBadge, "Updated 2 days ago (24 Nov 2026)". The badge reflects the **forecast** direction; the % line is **past** change. Label both clearly so they aren't confused.
4. **4-week outlook:** one plain-English sentence ("Expected to rise ~12% in 2 weeks"), then ForecastChart (26 weeks actual solid + 4 weeks dashed, P10–P90 band, vertical "Today" marker, baseline toggle off by default).
5. **Why prices are moving:** DriversList, top 2–3 drivers with impact bars.
6. **Best nearby mandi** card (F6) once available.
7. **Fixed bottom tab bar:** Home · Explore · Forecast · Accuracy · More. Icon + full label (no truncation like "Acc"); use "More" for Analytics and Status.

### 6.2 Desktop (max 1200 px) — trader & analyst view
- **Left rail (220 px fixed):** brand mark; vertical nav (Overview, Price Explorer, 4-Week Forecast, Analytics, Model Accuracy, Ingestion Status); footer with last successful data sync time and job status.
- **Top context header:** commodity + mandi selector pills, plus a secondary "Download weekly CSV" button.
- **Main canvas, 12-column grid:**
  - **Top row (3 × 4 cols):**
    1. Current modal price + week-on-week change + SignalBadge.
    2. 2-week forecast (P50), e.g. ₹2,620, with range "₹2,410 – ₹2,850 (P10–P90)".
    3. Best nearby mandi net of transport, e.g. "Pimpalgaon: +₹140/qtl net", with the transport-cost assumption in a tooltip/footnote.
  - **Middle row (8 + 4 cols):** ForecastChart (left), DriversList (right).
  - **Bottom row (12 cols):** multi-mandi compare chart + ledger table, up to 4 markets toggled via legend chips.

### 6.3 Dedicated pages
- **Accuracy (`/accuracy`):** Model-vs-baseline scorecard at top (MAPE, MASE, P10–P90 coverage by horizon; bold the better value per cell). Below it, a **"Forecast vs actual replay"** chart: past P10–P90 bands overlaid with the actual prices that followed. Show the number of evaluated forecasts and the date range; if fewer than 4 weeks of live forecasts exist, say so and show backtest results labelled as backtest.
- **Analytics (`/analytics`):** 2-column bento grid: seasonality heatmap (month × year, single-hue scale to `primary`) beside the rainfall-deviation vs price-change chart (lagged), followed by 3–5 key findings as bullets. Stacks to one column on mobile.
- **Status (`/status`):** last 14 ingestion runs (date, rows fetched, rows inserted, status) and per-series freshness.

## 7. Key components

- **PriceCard:** market name, current weekly price (display size), week-on-week change, signal badge, last updated.
- **SignalBadge:** pill with icon + text ("Rising", "Stable", "Falling"); never colour only.
- **ForecastChart:** last 26 weeks actual (solid) + 4 weeks forecast (dashed) + P10–P90 band + optional baseline toggle. Vertical "today" marker.
- **DriversList:** top 3 drivers as plain-English sentences with a small bar for impact size.
- **CompareChart:** up to 4 mandis, shared y-axis, legend chips you can toggle.
- **Heatmap:** month × year seasonality, single-hue sequential scale (light → `primary`).
- **AccuracyTable:** horizon × commodity, MAPE and MASE, model vs baseline, better value bolded.
- **StaleBanner:** amber bar at top of a card when the series is > 7 days old.
- **EmptyState / ErrorState:** short message + retry button; no stock illustrations.

## 8. Charts

- Recharts, consistent across the app: 12 px axis labels, light grid lines only on the y-axis, no 3D, no pie charts.
- Y-axis in ₹ with compact labels (`₹2.3k`); tooltip shows the full value.
- Always label units and the date range.
- **Direct labels instead of relying on hover** (tooltips are awkward on touchscreens): a value badge on the last actual point (`₹2,340`) and on the final forecast P50 point (`₹2,620`). Keep tooltips as a bonus on desktop.
- If two direct labels would overlap on mobile, keep the forecast label and drop the other into the card header.

## 8a. Tables (ledger style)

- Used in Explorer, Compare and Accuracy.
- Subtle horizontal hairlines only (`border` colour), no vertical lines, no zebra stripes.
- Text columns (market, commodity) left-aligned; all number columns right-aligned with tabular numerals so ₹ values and percentages line up.
- Header row in label style (13 px, 500, `text-muted`); sticky header on long tables.
- On mobile, tables with more than 3 columns scroll horizontally *inside the card* with the first column pinned; the page itself never scrolls sideways.

## 9. Interaction & states

- Skeleton loaders that match the card shapes (no spinners for whole pages).
- Tap targets ≥ 44 px.
- Respect `prefers-reduced-motion`; keep transitions ≤ 150 ms.
- Forecast pages show a short disclaimer: "Forecasts are estimates, not guarantees. See Accuracy for past performance."

## 10. Tone of copy

- Plain, short and specific: "Onion at Lasalgaon is expected to rise about 12% over the next 2 weeks."
- No hype words ("AI-powered", "revolutionary") in the UI.
- Explain drivers in everyday language: "Fewer arrivals than usual" instead of "lag_2_arrivals".
