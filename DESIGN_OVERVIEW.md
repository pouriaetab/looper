# LOOPER React App Design Overview

## Layout Architecture

```
┌─────────────────────────────────────────────────────┐
│  LOOPER  🔁  (Phase 3 — portfolio of active loops)  │
│                              [↻ Refresh] [☰ Toggle]  │
└─────────────────────────────────────────────────────┘

┌──────────────────────┬─────────────────────────────────┐
│   SIDEBAR            │   MAIN CONTENT                  │
│   (280px, fixed)     │   (flex, grows)                 │
│                      │                                 │
│  📋 Add / Update     │  ┌─────────────────────────────┐│
│     Position         │  │  🔴 SELL WATCH (3)          ││
│                      │  │  Positions you hold         ││
│  [Symbol box]        │  │                             ││
│  [Entry $ $ box]     │  │ ┌─────────────────────────┐ ││
│  [Shares box]        │  │ │ 🔥 SELL SIGNAL │ NVDA  │ ││
│  [Status dropdown]   │  │ │ $456.78 (+23%)  Expand ││ ││
│  [Target $ $ box]    │  │ └─────────────────────────┘ ││
│  [+ Add to Portfolio]│  │ ┌─────────────────────────┐ ││
│                      │  │ │ ⚠️ WATCH │ AVGO       │ ││
│  ───────────────────  │  │ │ $489.12 (+10%) Expand ││ ││
│  📊 Portfolio (2)     │  │ └─────────────────────────┘ ││
│                      │  │                             ││
│  NVDA holding        │  ├─────────────────────────────┤│
│    (@$400 × 1) 🔴   │  │  🟢 RE-ENTRY ZONES (1)      ││
│  [remove]            │  │  Cash waiting to re-enter   ││
│                      │  │                             ││
│  AVGO holding        │  │ ┌─────────────────────────┐ ││
│    (@$450 × 1) 🟢   │  │ │ RE-ENTRY ZONE │ TSLA   │ ││
│  [remove]            │  │ │ $235.40 (-5%)  Expand ││ ││
│                      │  │ └─────────────────────────┘ ││
│                      │  │                             ││
│                      │  └─────────────────────────────┘│
│                      │                                 │
│                      │  🔍 Candidate Scanner (coming) │
│                      │  Quality stocks oversold/overbought
└──────────────────────┴─────────────────────────────────┘
```

## Visual Design Elements

### Colors
- **🔴 Sell Watch** — Red badges for overbought positions
- **🟢 Re-entry Zones** — Green badges for oversold re-entry opportunities
- **🔥 Urgency** — Red for high urgency, ⚠️ orange for medium, • gray for low
- **Stance colors** — Accumulate (green), Hold (blue), Trim (orange), Exit (red)

### Card Design
- Clean white cards with subtle border
- Hover effect: shadow deepens, border darkens slightly
- Expandable detail rows with RSI, EMA, signal counts
- "Analyze ▸" button for full detail page

### Form Design
- Clear field labels
- Grouped inputs (Entry Price & Shares side-by-side)
- Dropdown for position status with clear options
- Success/error messages with inline color feedback
- Portfolio list showing current holdings with status badges

### Mobile Design
- Single-column layout on phones < 900px
- Full-width sidebar above content on small screens
- Touch-friendly buttons (8px padding minimum)
- Readable font sizes on all screens

---

## User Workflows

### Workflow 1: Add a New Position
```
1. User enters symbol (NVDA)
2. Enters entry price ($400)
3. Enters shares (1)
4. Selects status (🔴 Holding)
5. Optionally sets analyst target ($500)
6. Clicks "Add to Portfolio"
7. ✅ Success message appears
8. Position appears in Sell Watch section
```

### Workflow 2: View Sell Signals
```
1. User sees NVDA in Sell Watch (high urgency 🔥)
2. RSI is overbought (>72), starting to roll over
3. Price near analyst target
4. Clicks "Analyze ▸" to drill into detail
5. Sees full scorecard + all signal reasons
6. Re-entry plan shows:
   - Original cost: $400
   - Profit if sold now: +$56.78
   - Reserve for re-entry: $400 + 50% × $56.78 = $428.39
   - Can buy 1 whole share + 0.10 fractional at $420 level
```

### Workflow 3: Mark Position as Sold
```
1. User clicks "Analyze ▸" on NVDA
2. Sees detail page with current signals
3. (Future: button to mark sold from detail page)
4. User edits in sidebar → changes status to "🟢 Sold"
5. System calculates re-entry plan with realized price
6. Position moves to Re-entry Zones section
7. Shows next entry zones + sizing recommendations
```

### Workflow 4: Check Phone for Quick Status
```
1. User opens http://192.168.1.x:5173 on phone (WiFi)
2. Sees responsive layout: one column
3. Sell Watch shows 🔴 positions needing attention
4. Re-entry Zones show 🟢 cash waiting
5. Can tap "Analyze" to see details
6. Can use sidebar form to add new positions on the go
```

---

## Technical Details

### Component Structure
```
App.jsx (main)
├── topbar (title, refresh, toggle)
├── layout (sidebar + content flex)
│   ├── AddHolding.jsx (form + portfolio list)
│   └── content (Portfolio or StockDetail)
│       ├── Portfolio.jsx (Sell + Buy sections)
│       └── StockDetail.jsx (full analysis page)
└── footer (disclaimer)
```

### CSS Variables
```css
--bg: #fafaf8          /* main background */
--surface: #ffffff     /* cards, inputs */
--surface-alt: #f5f5f3 /* hover, focus states */
--border: #ebe9e4      /* dividers, input borders */
--text: #1a1a18        /* primary text */
--text-secondary: #6b6b66 /* muted labels, help text */
--accent: #1f4e8c      /* primary brand color */
--success: #0b6e3b     /* green badges */
--warning: #c77700     /* orange badges */
--danger: #b00020      /* red badges */
```

### Responsive Breakpoints
- **Mobile** — < 760px: single column, full-width sidebar
- **Tablet** — 760px–900px: sidebar + content in flex, adjusted gaps
- **Desktop** — > 900px: 280px fixed sidebar, full portfolio grid

---

## Future Enhancements

### Phase 4 — Candidate Scanner
Empty placeholder ready for:
- Screen for quality stocks that are oversold/overbought
- Show entry opportunities across universe of stocks
- Filter by sector, market cap, volatility
- Sort by LOOPER readiness score

### Dark Mode
- CSS variables ready for theme switching
- Just swap color values for dark theme

### Alerts / Notifications
- Toast notifications for sell/re-entry signals
- Optional email/SMS when signals fire
- Desktop notifications on page

### Export / History
- Export portfolio as CSV
- Historical trade log
- Performance metrics
