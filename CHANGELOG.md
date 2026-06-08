# LOOPER Changelog

## 2026-06-08 — React UI redesign + enhanced form

### What changed
- **Modern Cowork aesthetics** — CSS redesigned with refined colors, better spacing, subtle shadows, and improved visual hierarchy
- **Enhanced form design** — AddHolding sidebar now has:
  - Clear labels and placeholder text for each field
  - Better visual grouping of related fields (Price & Shares side-by-side)
  - Success/error messages with color-coded feedback
  - Improved portfolio list showing current holdings with status badges
- **Better portfolio sections** — Sell and Buy sections now clearly display:
  - Urgency indicators (🔥 high, ⚠️ medium, • low)
  - Clean card design with hover effects
  - Expanded detail view showing RSI, EMAs, signal counts, and recommended action
  - Placeholder for future "Candidate Scanner" (Phase 4)
- **Responsive design** — Improved mobile layout with better touch targets and readability on phones
- **Form validation** — Added checks for valid entry prices and share counts with user-friendly error messages

### Features still working
- ✅ Two-section portfolio (🔴 Sell watch + 🟢 Re-entry zones)
- ✅ Add/update holdings via sidebar form
- ✅ Profit allocation (original cost + 50% of profit reserved for re-entry)
- ✅ Re-entry sizing calculations (whole + fractional shares at support levels)
- ✅ Per-stock detail pages with full scoring & timing signals
- ✅ Fundamental scorecard with Quality/Valuation/Health/Growth factors
- ✅ Analyst targets and consensus data
- ✅ News digest and sentiment analysis
- ✅ Earnings and catalyst tracking

### Backend unchanged
- FastAPI endpoints remain the same
- Engine logic (signals, scoring, re-entry math) unchanged
- Config structure compatible (no migration needed)

### Tech notes
- CSS variables for theming (easy dark mode later if needed)
- Better focus states for form accessibility
- Mobile-first responsive grid
- Subtle animations on card hover

### Next: Phase 4
- Candidate scanner — screen for quality stocks that are oversold/overbought
- Entry automation (optional)
- Alert system for sell/re-entry signals
