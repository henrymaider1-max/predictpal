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
MIN_EDGE          = 0.03   # minimum edge to place a trade (3%)
MAX_TRADE_PCT     = 0.05   # never risk more than 5% of bankroll
KELLY_FRACTION    = 0.5    # Half-Kelly for safety
MAX_OPEN_TRADES   = 20     # cap simultaneous open positions

# ── Load / initialise bankroll ──────────────────────────────────────────────
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

# ── Load trade history ─────────────────────────────────────────────────────────────
def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            return json.load(f)
    return {"trades": []}

def save_trades(t):
    with open(TRADES_FILE, "w") as f:
        json.dump(t, f, indent=2)

# ── AI probability estimator ────────────────────────────────────────────────────────
def estimate_true_prob(market, all_markets):
    """
    Multi-signal probability estimator:
    1. Start with the market price.
    2. Apply a mean-reversion nudge for very thin or very extreme markets.
    3. Cross-platform consensus: if another platform prices the same event
       differently, weight toward the higher-volume platform.
    4. Volume confidence: low volume -> nudge toward 50%.
    """
    base = market["prob_yes"]
    volume = market.get("volume", 0) or 0
    platform = market["platform"]
    title_words = set(market["title"].lower().split())

    # --- Signal 1: cross-platform consensus ---
    peer_probs = []
    peer_vols  = []
    for m in all_markets:
        if m["id"] == market["id"]:
            continue
        if m["platform"] == platform:
            continue
        other_words = set(m["title"].lower().split())
        overlap = len(title_words & other_words) / max(len(title_words | other_words), 1)
        if overlap >= 0.55:
            peer_probs.append(m["prob_yes"])
            peer_vols.append(m.get("volume", 0) or 0)

    if peer_probs:
        total_vol = sum(peer_vols) + max(volume, 1)
        our_weight = max(volume, 1) / total_vol
        peer_weight = 1 - our_weight
        peer_avg = sum(p * v for p, v in zip(peer_probs, peer_vols)) / max(sum(peer_vols), 1)
        base = our_weight * base + peer_weight * peer_avg

    # --- Signal 2: volume confidence ---
    if volume < 500:
        # Very thin market -> nudge 15% toward 50%
        base = base * 0.85 + 0.5 * 0.15
    elif volume < 5000:
        # Moderate volume -> nudge 5% toward 50%
        base = base * 0.95 + 0.5 * 0.05

    # --- Signal 3: extreme probability correction ---
    # Markets priced >97% or <3% are often overconfident
    if base > 0.97:
        base = 0.97
    elif base < 0.03:
        base = 0.03

    return round(base, 4)

# ── Kelly bet sizing ───────────────────────────────────────────────────────────────────
def kelly_size(bankroll, true_prob, market_prob, side="YES"):
    """
    Kelly formula: f = (p*b - q) / b
    b = net odds (payout per $1 risked)
    Returns dollar amount to bet.
    """
    if side == "YES":
        p = true_prob
        q = 1 - p
        b = (1 - market_prob) / max(market_prob, 0.001)
    else:
        p = 1 - true_prob
        q = 1 - p
        b = market_prob / max(1 - market_prob, 0.001)

    kelly_f = (p * b - q) / b
    if kelly_f <= 0:
        return 0.0
    fractional = kelly_f * KELLY_FRACTION
    capped = min(fractional, MAX_TRADE_PCT)
    return round(bankroll * capped, 2)

# ── Main trading loop ──────────────────────────────────────────────────────────────────
def run_engine():
    if not os.path.exists(MARKETS_FILE):
        print("No markets data found. Run fetch_markets.py first.")
        return

    with open(MARKETS_FILE) as f:
        mdata = json.load(f)

    all_markets = mdata["markets"]
    bankroll_data = load_bankroll()
    trades_data   = load_trades()
    balance = bankroll_data["balance"]
    new_trades = 0

    # De-duplicate market IDs already in open trades
    open_ids = {t["market_id"] for t in trades_data["trades"] if t["status"] == "open"}

    # Sort markets by volume descending (most liquid first)
    sorted_markets = sorted(all_markets, key=lambda m: m.get("volume", 0) or 0, reverse=True)

    for market in sorted_markets:
        # Stop if we've hit the open position cap
        if len(open_ids) >= MAX_OPEN_TRADES:
            break

        mid = market.get("id")
        if mid in open_ids:
            continue

        # Skip markets with no real probability signal
        market_prob = market["prob_yes"]
        if market_prob <= 0 or market_prob >= 1:
            continue

        true_prob = estimate_true_prob(market, all_markets)
        edge_yes = true_prob - market_prob
        edge_no  = (1 - true_prob) - (1 - market_prob)  # same as market_prob - true_prob
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
            "potential_profit": round(
                bet_amount * ((1 / market_prob if side == "YES" else 1 / (1 - market_prob)) - 1), 2
            ),
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
        print(f"  TRADE: {side} {market['platform']} | edge={best_edge:.3f} | ${bet_amount} | {market['title'][:60]}")

    # Update bankroll
    bankroll_data["balance"]      = round(balance, 2)
    bankroll_data["peak"]         = round(max(bankroll_data["peak"], balance), 2)
    bankroll_data["total_trades"] += new_trades
    save_bankroll(bankroll_data)
    save_trades(trades_data)
    print(f"Engine run complete: {new_trades} new paper trades. Balance: ${balance:,.2f}")

if __name__ == "__main__":
    run_engine()
