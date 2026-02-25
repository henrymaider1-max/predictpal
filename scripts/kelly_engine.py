"""
PredictPal Kelly Criterion Paper Trading Engine (Pro Mode)
Scans markets, analyzes 'Smart Money' pro bets, finds edge, and logs trades.
Prioritizes short-term sports, politics, and market events.
"""
import json, math, os
from datetime import datetime, timezone, timedelta

BANKROLL_FILE = "data/bankroll.json"
TRADES_FILE   = "data/trades.json"
MARKETS_FILE  = "data/markets.json"
PRO_BETS_FILE = "data/pro_bets.json"
NOW_DT = datetime.now(timezone.utc)
NOW = NOW_DT.isoformat()

# --- Pro Aggressive Settings ---
STARTING_BANKROLL = 100_000.0
MIN_EDGE          = 0.015  # Very aggressive: 1.5% edge threshold
MAX_TRADE_PCT     = 0.10   # High risk: 10% max bankroll per trade
KELLY_FRACTION    = 0.7    # Aggressive Kelly: 0.7 sizing
MAX_OPEN_TRADES   = 60     # High volume: up to 60 open slots

# ── Load / initialise data ──────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except: return default
    return default

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

# ── AI probability estimator (Smart Money Integrated) ────────────────────────
def estimate_true_prob(market, all_markets, pro_bets):
    base = market["prob_yes"]
    mid = market["id"]
    volume = market.get("volume", 0) or 0
    category = (market.get("category") or "general").lower()
    
    # --- Signal 1: Smart Money (Pro Bets) ---
    # This is the strongest nudge. If top traders are betting, we follow.
    pro_signal = 0
    for bet in pro_bets:
        if bet["market_id"] == mid or bet["market_id"] in mid:
            # Polymarket outcome 0 is usually 'Yes', 1 is 'No'
            # Adjust probability based on pro bet direction
            if bet["side"] == "BUY":
                pro_signal += 0.08 if bet["outcome"] == "0" else -0.08
            else: # SELL
                pro_signal += -0.05 if bet["outcome"] == "0" else 0.05
    
    base += pro_signal

    # --- Signal 2: Category Confidence Nudge ---
    active_cats = ['sports', 'nba', 'mlb', 'politics', 'fed', 'crypto', 'stocks']
    is_preferred = any(c in category for c in active_cats)
    if is_preferred and volume < 5000:
        # Nudge toward 50% for thin markets to create edge vs overconfident prices
        base = base * 0.85 + 0.5 * 0.15
        
    return round(max(0.01, min(0.99, base)), 4)

# ── Kelly bet sizing ─────────────────────────────────────────────────────────
def kelly_size(bankroll, true_prob, market_prob, side="YES"):
    if side == "YES":
        p, b = true_prob, (1 - market_prob) / max(market_prob, 0.001)
    else:
        p, b = 1 - true_prob, market_prob / max(1 - market_prob, 0.001)
    
    q = 1 - p
    kelly_f = (p * b - q) / b
    if kelly_f <= 0: return 0.0
    return round(bankroll * min(kelly_f * KELLY_FRACTION, MAX_TRADE_PCT), 2)

# ── Main trading loop ────────────────────────────────────────────────────────
def run_engine():
    mdata = load_json(MARKETS_FILE, {"markets": []})
    if not mdata["markets"]: return
    
    pbets = load_json(PRO_BETS_FILE, {"bets": []}).get("bets", [])
    bankroll_data = load_json(BANKROLL_FILE, {"balance": STARTING_BANKROLL, "total_trades": 0})
    trades_data = load_json(TRADES_FILE, {"trades": []})
    
    balance = bankroll_data["balance"]
    new_trades = 0
    open_ids = {t["market_id"] for t in trades_data["trades"] if t["status"] == "open"}

    def market_score(m):
        score = 0
        mid = m["id"]
        # 1. HUGE BONUS: Smart Money follows (+200 points)
        if any(b["market_id"] == mid for b in pbets): score += 200
        
        # 2. Short-term bonus (same day / 24hr)
        end_str = m.get("end_date")
        if end_str:
            try:
                end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                hours_left = (end_dt - NOW_DT).total_seconds() / 3600
                if 0 < hours_left < 12: score += 150 # Extreme priority for same-day
                elif 12 <= hours_left < 48: score += 70
            except: pass
            
        # 3. Category match
        cat = (m.get("category") or "").lower()
        if any(c in cat for c in ['sports', 'nba', 'mlb', 'politics', 'fed']): score += 100
        return score

    sorted_markets = sorted(mdata["markets"], key=market_score, reverse=True)

    for market in sorted_markets:
        if len(open_ids) >= MAX_OPEN_TRADES: break
        mid = market["id"]
        if mid in open_ids: continue

        market_prob = market["prob_yes"]
        true_prob = estimate_true_prob(market, mdata["markets"], pbets)
        
        edge_yes = true_prob - market_prob
        edge_no = (1 - true_prob) - (1 - market_prob)
        best_edge = max(edge_yes, edge_no)

        if best_edge < MIN_EDGE: continue

        side = "YES" if edge_yes >= edge_no else "NO"
        bet_amount = kelly_size(balance, true_prob, market_prob, side)

        if bet_amount < 5: continue

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
            "pro_money": any(b["market_id"] == mid for b in pbets),
            "status": "open",
            "placed_at": NOW,
        })
        balance -= bet_amount
        open_ids.add(mid)
        new_trades += 1
        print(f"  PRO TRADE: {side} | {market['title'][:45]} | Edge: {best_edge:.3f}")

    bankroll_data["balance"] = round(balance, 2)
    bankroll_data["total_trades"] += new_trades
    save_json(BANKROLL_FILE, bankroll_data)
    save_json(TRADES_FILE, trades_data)
    print(f"Engine Run Done: {new_trades} new trades.")

if __name__ == "__main__":
    run_engine()
