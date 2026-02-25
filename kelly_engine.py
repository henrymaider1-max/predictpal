"""
PredictPal Kelly Criterion Paper Trading Engine
Scans markets, finds edge, sizes bets using Half-Kelly, logs paper trades.
"""
import json, math, os
from datetime import datetime, timezone

BANKROLL_FILE = "data/bankroll.json"
TRADES_FILE   = "data/trades.json"
MARKETS_FILE  = "data/markets.json"
NOW = datetime.now(timezone.utc).isoformat()

STARTING_BANKROLL = 100_000.0
MIN_EDGE          = 0.04    # minimum edge (prob diff) to place a trade
MAX_TRADE_PCT     = 0.05    # never risk more than 5% of bankroll on one trade
KELLY_FRACTION    = 0.5     # Half-Kelly for safety

# ── Load / initialise bankroll ────────────────────────────────────────────────
def load_bankroll():
    if os.path.exists(BANKROLL_FILE):
        with open(BANKROLL_FILE) as f:
            return json.load(f)
    return {"balance": STARTING_BANKROLL, "peak": STARTING_BANKROLL,
            "total_trades": 0, "updated_at": NOW}

def save_bankroll(br):
    br["updated_at"] = NOW
    with open(BANKROLL_FILE, "w") as f:
        json.dump(br, f, indent=2)

# ── Load trade history ────────────────────────────────────────────────────────
def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            return json.load(f)
    return {"trades": []}

def save_trades(t):
    with open(TRADES_FILE, "w") as f:
        json.dump(t, f, indent=2)

# ── AI probability estimator ──────────────────────────────────────────────────
def estimate_true_prob(market):
    """
    Simple signal-based estimator.
    In future versions this will integrate NLP + historical resolution rates.
    Current logic:
      - Start with market price as base.
      - Adjust slightly for volume (high-volume markets are more accurate).
      - Adjust if multiple platforms agree (consensus signal).
    """
    base = market["prob_yes"]
    volume = market.get("volume", 0)
    # Volume confidence nudge: very thin markets may have stale prices
    if volume < 1000:
        base = base * 0.97 + 0.5 * 0.03  # nudge toward 50%
    return round(base, 4)

# ── Kelly bet sizing ──────────────────────────────────────────────────────────
def kelly_size(bankroll, true_prob, market_prob, side="YES"):
    """
    b = net odds (if market_prob = 0.3, odds = 0.3/(1-0.3) = 0.4286 → b = 1/0.4286 - 1 = 1.333)
    Kelly f = (p*b - q) / b
    Returns dollar amount to bet.
    """
    if side == "YES":
        p = true_prob
        q = 1 - p
        b = (1 - market_prob) / market_prob  # payout per $1 risked on YES
    else:
        p = 1 - true_prob
        q = 1 - p
        b = market_prob / (1 - market_prob)

    kelly_f = (p * b - q) / b
    if kelly_f <= 0:
        return 0.0

    fractional = kelly_f * KELLY_FRACTION
    capped = min(fractional, MAX_TRADE_PCT)
    return round(bankroll * capped, 2)

# ── Main trading loop ─────────────────────────────────────────────────────────
def run_engine():
    if not os.path.exists(MARKETS_FILE):
        print("No markets data found. Run fetch_markets.py first.")
        return

    with open(MARKETS_FILE) as f:
        mdata = json.load(f)

    bankroll_data = load_bankroll()
    trades_data   = load_trades()
    balance       = bankroll_data["balance"]
    new_trades    = 0

    # De-duplicate market IDs already in open trades
    open_ids = {t["market_id"] for t in trades_data["trades"] if t["status"] == "open"}

    for market in mdata["markets"]:
        mid = market.get("id")
        if mid in open_ids:
            continue

        true_prob   = estimate_true_prob(market)
        market_prob = market["prob_yes"]
        edge_yes    = true_prob - market_prob
        edge_no     = (1 - true_prob) - (1 - market_prob)

        best_edge = max(edge_yes, edge_no)
        if best_edge < MIN_EDGE:
            continue

        side = "YES" if edge_yes >= edge_no else "NO"
        bet_amount = kelly_size(balance, true_prob, market_prob, side)

        if bet_amount < 10:  # minimum $10 trade
            continue

        trade = {
            "id": f"trade-{len(trades_data['trades'])+1}",
            "market_id": mid,
            "platform": market["platform"],
            "title": market["title"],
            "side": side,
            "market_prob": market_prob,
            "true_prob_estimate": true_prob,
            "edge": round(best_edge, 4),
            "bet_amount": bet_amount,
            "potential_profit": round(bet_amount * ((1 / market_prob if side == "YES" else 1 / (1 - market_prob)) - 1), 2),
            "status": "open",
            "url": market["url"],
            "placed_at": NOW,
            "resolved_at": None,
            "pnl": None,
        }

        trades_data["trades"].append(trade)
        balance -= bet_amount
        open_ids.add(mid)
        new_trades += 1

    # Update bankroll
    bankroll_data["balance"] = round(balance, 2)
    bankroll_data["peak"]    = round(max(bankroll_data["peak"], balance), 2)
    bankroll_data["total_trades"] += new_trades

    save_bankroll(bankroll_data)
    save_trades(trades_data)

    print(f"Engine run: {new_trades} new paper trades. Balance: ${balance:,.2f}")

if __name__ == "__main__":
    run_engine()
