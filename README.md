# PredictPal 🎯

**Prediction market intelligence dashboard** — track live markets across Polymarket, Kalshi, Manifold, and Metaculus. Find arbitrage, follow top traders, and let the AI paper-trade with a $100k virtual bankroll.

## Features
- 📊 Live markets from 4 platforms, normalized to implied probability
- ⚡ Cross-platform arbitrage detector
- 🔍 Polymarket wallet tracker (high-profit traders)
- 🤖 AI paper trading engine using Half-Kelly criterion

## Setup

### 1. Fork / Clone this repo
```bash
git clone https://github.com/YOUR_USERNAME/predictpal
cd predictpal
```

### 2. Enable GitHub Pages
- Go to **Settings → Pages**
- Set source to **Deploy from branch: `main` / root**

### 3. Enable GitHub Actions
- Go to **Settings → Actions → General**
- Allow all actions
- Under **Workflow permissions**, select **Read and write permissions**

### 4. Trigger the first data fetch
- Go to **Actions → Fetch Market Data → Run workflow**
- Then **Actions → Run Kelly Engine → Run workflow**

### 5. Visit your site
`https://YOUR_USERNAME.github.io/predictpal`

## File Structure
```
predictpal/
├── index.html              # Main dashboard
├── css/style.css           # Dark theme styles
├── js/app.js               # Frontend logic
├── scripts/
│   ├── fetch_markets.py    # Data fetcher (runs every 15 min via Action)
│   └── kelly_engine.py     # Paper trading engine
├── data/
│   ├── markets.json        # All live markets (auto-updated)
│   ├── traders.json        # Top Polymarket traders
│   ├── arbitrage.json      # Detected arb opportunities
│   ├── trades.json         # Paper trade history
│   └── bankroll.json       # Virtual bankroll state
└── .github/workflows/
    ├── fetch-markets.yml   # Runs every 15 min
    └── run-engine.yml      # Runs after each data fetch
```

## Roadmap
- [ ] Kalshi/Manifold trader tracking
- [ ] NBA/sports market filter
- [ ] Historical resolution rate per platform
- [ ] Real trade execution via API
- [ ] Trader copy-follow alerts
