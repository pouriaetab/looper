# Run LOOPER Locally on Your Machine

The `./run.sh` script needs to run **on your local Mac/computer**, not in Cowork (which has no internet).

## One-Time Setup (First time only)

In VS Code terminal, from your looper folder:

```bash
# 1. Create virtual environment
python3 -m venv venv

# 2. Activate it
source venv/bin/activate

# 3. Install backend dependencies (FastAPI, uvicorn, requests)
pip install -r requirements.txt

# 4. Install frontend dependencies
cd frontend
npm install
cd ..
```

This takes ~2-3 minutes. Do it once, then you're done.

---

## Run the App (Every time you want to test)

From the looper folder, just one command:

```bash
./run.sh
```

That's it! This will:
- ✅ Activate venv
- ✅ Start FastAPI backend (port 8000)
- ✅ Start React frontend (port 5173)
- ✅ Open http://localhost:5173 in your browser
- ✅ Show you the API docs at http://localhost:8000/docs

Then you'll see:
```
╔════════════════════════════════════════════════════════════╗
║                   ✅ LOOPER is running                     ║
╚════════════════════════════════════════════════════════════╝

  📱 Open your browser:  http://localhost:5173
  📊 API docs:          http://localhost:8000/docs
  🔧 Backend:           running on :8000
  ⚛️  Frontend:           running on :5173
  Press Ctrl+C to stop all services
```

---

## Export Your Massive API Key (Security)

Before the first run, set your API key in your shell environment (never in code):

```bash
# Open your shell config
code ~/.zshrc

# Add this line at the bottom (paste your real key):
export MASSIVE_API_KEY="your_key_here"

# Reload shell
source ~/.zshrc

# Verify it's set (prints "key is set" without revealing the key):
[ -n "$MASSIVE_API_KEY" ] && echo "key is set"
```

The backend will read this environment variable automatically.

---

## Test with BRKR

1. Open http://localhost:5173
2. You should see BRKR pre-loaded in the **Sell Watch** section
3. Current price, RSI, timing signals should show
4. Click **Analyze ▸** to see full scoring + re-entry plan

---

## Add More Stocks

Use the **Add / Update Position** form in the sidebar:
- Symbol (e.g., NVDA, AVGO)
- Entry price you paid
- Number of shares
- Status (Holding or Sold)
- Optional: analyst target

Click "Add to Portfolio" → appears in Sell or Buy section.

---

## Test on Your Phone

Want to view on your phone (same WiFi)?

```bash
# Modify the run.sh to pass --host flag, OR manually:

# Terminal 1:
source venv/bin/activate
uvicorn api:app --reload --port 8000

# Terminal 2:
cd frontend
npm run dev -- --host
```

Then open the Network URL it shows on your phone.

---

## Schedule Daily Runs (Later)

Once stable, set `python looper_engine.py` to run each evening via cron/launchd:

```bash
# This runs the engine (no tokens, no Claude), writes data/portfolio.json
# The React app just displays the latest cached results
python looper_engine.py
```

Then the dashboard is just a viewer with no cost.

---

## Troubleshooting

**Backend won't start?**
```bash
# Check if something is already using port 8000
lsof -i :8000

# Kill it if needed
kill -9 <PID>

# Then run ./run.sh again
```

**Frontend won't start?**
```bash
# Make sure you're in the frontend folder
cd frontend
npm run dev
```

**API key not found?**
```bash
# Verify it's exported
echo $MASSIVE_API_KEY

# If blank, reload your shell:
source ~/.zshrc
```

**Dependencies not installing?**
```bash
# Make sure you have internet & you're in the looper folder
pip install --upgrade pip
pip install -r requirements.txt
```

---

That's it! Everything runs locally now. No Claude, no tokens, just fast trading signals. 🚀
