"""
PredictPal Kelly Criterion Paper Trading Engine
Scans markets, finds edge, sizes bets using Half-Kelly, logs paper trades.
"""
import json, math, os
from datetime import datetime, timezone, timedelta

BANKROLL_FILE = "data/bankroll.json"
TRADES_FILE   = "data/trades.json"
MARKETS_FILE  = "data/markets.json"
NOW_DT = datetime.now(timezone.utc)
NOW = NOW_DT.isoformat()

# --- Aggressive Settings ---
STARTING_BANKROLL = 100_000.0
MIN_EDGE          = 0.02   # Lowered to 2% for more activity
MAX_TRADE_PCT     = 0.08   # Increased to 8% (was 5%)
KELLY_FRACTION    = 0.6    # Increased to 0.6-Kelly (was 0.5)
MAX_OPEN_TRADES   = 40     # Doubled position limit (was 20)

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
    base = market["prob_yes"]
    volume = market.get("volume", 0) or 0
    platform = market["platform"]
    category = (market.get("category") or "general").lower()
    title_words = set(market["title"].lower().split())

    # --- Signal 1: cross-platform consensus ---
    peer_probs = []
    peer_vols  = []
    for m in all_markets:
        if m["id"] == market["id"]: continue
        if m["platform"] == platform: continue
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

    # --- Signal 2: Aggressive Nudge for Preferred Categories ---
    # We prefer Sports, Politics, and Markets
    active_cats = ['sports', 'nba', 'nfl', 'mlb', 'politics', 'crypto', 'stocks', 'finance']
    is_preferred = any(c in category for c in active_cats)
    
    if volume < 2000:
        nudge = 0.20 if is_preferred else 0.10
        base = base * (1 - nudge) + 0.5 * nudge

    return round(base, 4)

# ── Kelly bet sizing ───────────────────────────────────────────────────────────────────
def kelly_size(bankroll, true_prob, market_prob, side="YES"):
    if side == "YES":
        p, b = true_prob, (1 - market_prob) / max(market_prob, 0.001)
    else:
        p, b = 1 - true_prob, market_prob / max(1 - market_prob, 0.001)
    
    q = 1 - p
    kelly_f = (p * b - q) / b
    if kelly_f <= 0: return 0.0
    return round(bankroll * min(kelly_f * KELLY_FRACTION, MAX_TRADE_PCT), 2)

# ── Main trading loop ──────────────────────────────────────────────────────────────────
def run_engine():
    if not os.path.exists(MARKETS_FILE): return
    with open(MARKETS_FILE) as f: mdata = json.load(f)

    all_markets = mdata["markets"]
    bankroll_data = load_bankroll()
    trades_data   = load_trades()
    balance = bankroll_data["balance"]
    new_trades = 0
    open_ids = {t["market_id"] for t in trades_data["trades"] if t["status"] == "open"}

    # --- Aggressive Prioritization ---
    def market_score(m):
        score = 0
        # 1. Prefer short-term markets (closes in 12-48 hours)
        end_str = m.get("end_date")
        if end_str:
            try:
                # Handle various formats (ISO, Polymarket, etc)
                clean_end = end_str.replace('Z', '+00:00')
                end_dt = datetime.fromisoformat(clean_end)
                hours_left = (end_dt - NOW_DT).total_seconds() / 3600
                if 0 < hours_left < 24: score += 100
                elif 24 <= hours_left < 48: score += 50
            except: pass
        
        # 2. Prefer specific categories
        cat = (m.get("category") or "").lower()
        if any(c in cat for c in ['sports', 'nba', 'mlb', 'basketball', 'baseball']): score += 80
        if any(c in cat for c in ['politics', 'election']): score += 60
        if any(c in cat for c in ['stocks', 'crypto', 'finance']): score += 40
        
        # 3. Prefer volume (liquidity)
        score += math.log10(max(m.get("volume", 0), 1)) * 5
        return score

    sorted_markets = sorted(all_markets, key=market_score, reverse=True)

    for market in sorted_markets:
        if len(open_ids) >= MAX_OPEN_TRADES: break
        mid = market.get("id")
        if mid in open_ids: continue

        market_prob = market["prob_yes"]
        if market_prob <= 0.01 or market_prob >= 0.99: continue

        true_prob = estimate_true_prob(market, all_markets)
        edge_yes, edge_no = true_prob - market_prob, (1 - true_prob) - (1 - market_prob)
        best_edge = max(edge_yes, edge_no)

        if best_edge < MIN_EDGE: continue

        side = "YES" if edge_yes >= edge_no else "NO"
        bet_amount = kelly_size(balance, true_prob, market_prob, side)

        if bet_amount < 5: continue # Lowered min trade to $5

        trades_data["trades"].append({
            "id": f"trade-{len(trades_data['trades'])+1}",
            "market_id": mid,
            "platform": market["platform"],
            "title": market["title"],
            "side": side,
            "market_prob": market_prob,
            "true_prob_estimate": true_prob,
            "edge": round(best_edge, 4),
            "bet_amount": bet_amount,
            "potential_profit": round(bet_amount * ((1/market_prob if side=="YES" else 1/(1-market_prob))-1), 2),
            "status": "open",
            "url": market["url"],
            "placed_at": NOW,
        })
        balance -= bet_amount
        open_ids.add(mid)
        new_trades += 1
        print(f"  AGGRESSIVE TRADE: {side} {market['platform']} | edge={best_edge:.3f} | ${bet_amount} | {market['title'][:50]}")

    bankroll_data["balance"] = round(balance, 2)
    bankroll_data["total_trades"] += new_trades
    save_bankroll(bankroll_data)
    save_trades(trades_data)
    print(f"Engine complete: {new_trades} new trades.")

if __name__ == "__main__":
    run_engine()
