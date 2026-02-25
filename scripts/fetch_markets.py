"""
PredictPal Market Data Fetcher (Pro Mode)
Pulls data from Polymarket, Kalshi, Manifold, and Metaculus.
Now tracks 'Smart Money' by analyzing recent trades from top-ranked traders.
"""
import requests, json, time, os, re
from datetime import datetime, timezone, timedelta

HEADERS = {"User-Agent": "PredictPal/1.0"}
NOW_DT = datetime.now(timezone.utc)
NOW = NOW_DT.isoformat()

# -- helpers --------------------------------------------------------------------
def safe_get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f" [WARN] {url} attempt {i+1} failed: {e}")
            time.sleep(2)
    return None

def norm(platform, title, prob_yes, volume, url, end_date=None, category=None, market_id=None):
    return {
        "id": market_id or f"{platform}-{hash(title) & 0xFFFFFF}",
        "platform": platform,
        "title": title,
        "prob_yes": round(float(prob_yes), 4),
        "prob_no": round(1 - float(prob_yes), 4),
        "volume": volume,
        "url": url,
        "end_date": end_date,
        "category": category or "general",
        "fetched_at": NOW,
    }

# -- Polymarket ------------------------------------------------------------------
def fetch_polymarket(limit=400):
    markets = []
    # Specifically target high-velocity tags + requested sports
    tags = ["Sports", "Politics", "Crypto", "Fed", "Baseball", "Basketball", "NBA", "MLB"]
    for tag in tags:
        data = safe_get("https://gamma-api.polymarket.com/markets", params={
            "limit": 100,
            "active": "true",
            "closed": "false",
            "tag": tag,
            "_order": "volume24hr",
            "_sort": "desc"
        })
        if not data: continue
        items = data if isinstance(data, list) else data.get("markets", [])
        for m in items:
            try:
                prices = json.loads(m.get("outcomePrices", "[0.5,0.5]"))
                outcomes = json.loads(m.get("outcomes", '["Yes","No"]'))
                yes_idx = next((i for i, o in enumerate(outcomes) if o.lower() == "yes"), 0)
                markets.append(norm(
                    platform="Polymarket",
                    title=m.get("question", m.get("title", "")),
                    prob_yes=float(prices[yes_idx]),
                    volume=m.get("volumeNum", 0),
                    url=f"https://polymarket.com/event/{m.get('slug', '')}",
                    end_date=m.get("endDate"),
                    category=tag.lower(),
                    market_id=m.get("id"),
                ))
            except: pass
    print(f" Polymarket: {len(markets)} markets")
    return markets[:limit]

# -- Kalshi ----------------------------------------------------------------------
def fetch_kalshi(limit=400):
    markets = []
    data = safe_get("https://api.elections.kalshi.com/trade-api/v2/markets", params={
        "limit": limit,
        "status": "open"
    })
    if data:
        for m in data.get("markets", []):
            try:
                markets.append(norm(
                    platform="Kalshi",
                    title=m.get("title", ""),
                    prob_yes=m.get("yes_price", 50) / 100.0,
                    volume=m.get("volume", 0),
                    url=f"https://kalshi.com/markets/{m.get('event_ticker','').lower()}",
                    end_date=m.get("close_time"),
                    category=m.get("category", "general"),
                    market_id=m.get("ticker"),
                ))
            except: pass
    print(f" Kalshi: {len(markets)} markets")
    return markets[:limit]

# -- Manifold --------------------------------------------------------------------
def fetch_manifold(limit=400):
    markets = []
    data = safe_get("https://api.manifold.markets/v0/markets", params={
        "limit": limit,
        "sort": "liquidity"
    })
    if data:
        for m in (data if isinstance(data, list) else []):
            try:
                if m.get("outcomeType") != "BINARY": continue
                markets.append(norm(
                    platform="Manifold",
                    title=m.get("question", ""),
                    prob_yes=m.get("probability", 0.5),
                    volume=m.get("volume", 0),
                    url=m.get("url", ""),
                    end_date=m.get("closeTime"),
                    category="general",
                    market_id=m.get("id"),
                ))
            except: pass
    print(f" Manifold: {len(markets)} markets")
    return markets[:limit]

# -- Metaculus -------------------------------------------------------------------
def fetch_metaculus(limit=400):
    markets = []
    data = safe_get("https://www.metaculus.com/api2/questions/", params={
        "limit": limit,
        "order_by": "-activity",
        "status": "open",
        "type": "forecast"
    })
    if data:
        for m in data.get("results", []):
            try:
                cp = m.get("community_prediction", {})
                prob = cp.get("full", {}).get("q2", 0.5) if cp else 0.5
                markets.append(norm(
                    platform="Metaculus",
                    title=m.get("title", ""),
                    prob_yes=prob or 0.5,
                    volume=m.get("number_of_predictions", 0),
                    url=f"https://www.metaculus.com{m.get('page_url', '')}",
                    end_date=m.get("resolve_time"),
                    category="general",
                    market_id=str(m.get("id")),
                ))
            except: pass
    print(f" Metaculus: {len(markets)} markets")
    return markets[:limit]

# -- Smart Money: Top Trader Analysis -------------------------------------------
def fetch_trader_bets(limit=20):
    """
    Fetches the leaderboard, then looks at the *actual trades* for those traders.
    Filters for trades made in the last 24 hours in short-term categories.
    """
    leaderboard = safe_get("https://data-api.polymarket.com/activity", params={"limit": limit})
    if not leaderboard: return []
    traders_bets = []
    items = leaderboard if isinstance(leaderboard, list) else leaderboard.get("results", [])
    for t in items[:limit]:
        addr = t.get("proxyWallet", t.get("address", ""))
        if not addr: continue
        # Fetch actual recent trades for this trader
        trades = safe_get(f"https://data-api.polymarket.com/trades", params={
            "address": addr,
            "limit": 10
        })
        if not trades: continue
        trader_items = trades if isinstance(trades, list) else trades.get("results", [])
        for tr in trader_items:
            try:
                # We want trades in the last 24 hours
                trade_time = datetime.fromtimestamp(tr.get("timestamp", 0) / 1000, tz=timezone.utc)
                if (NOW_DT - trade_time).total_seconds() > 86400: continue
                traders_bets.append({
                    "trader": t.get("name", addr[:8]),
                    "market_id": tr.get("conditionId"),
                    "side": tr.get("side"),  # 'BUY' or 'SELL'
                    "outcome": tr.get("outcome"),  # outcome index
                    "size": tr.get("amount", 0),
                    "timestamp": tr.get("timestamp"),
                })
            except: pass
        time.sleep(0.3)  # be polite to API
    print(f" Smart Money: Found {len(traders_bets)} recent pro trades.")
    return traders_bets

# -- Improved Arbitrage Detector (Live Gaps) ------------------------------------
def find_arbitrage(all_markets, threshold=0.012):
    """
    Super-aggressive arb detector. Lowered threshold to 1.2% to catch live sports gaps.
    """
    arb_opportunities = []
    # Simplified core topic extraction inline for performance
    topics = []
    stopwords = {'will', 'be', 'at', 'least', 'more', 'than', 'less', 'by', 'before', 'after', 'in', 'on', 'of', 'the', 'a', 'an', 'to', 'for', 'is', 'as', 'and', 'or', 'not', 'end', 'close', 'above', 'below', 'over', 'under', 'reach', 'hit', 'have', 'has', 'win'}
    for m in all_markets:
        w = set(re.sub(r'[?.,!]', '', m["title"].lower()).split()) - stopwords
        topics.append((m, [x for x in w if len(x) > 2]))
    for i, (a, ta) in enumerate(topics):
        for j in range(i+1, len(topics)):
            b, tb = topics[j]
            if a["platform"] == b["platform"]: continue
            overlap = len(set(ta) & set(tb)) / max(len(set(ta) | set(tb)), 1)
            if overlap >= 0.25:
                diff = abs(a["prob_yes"] - b["prob_yes"])
                if diff >= threshold:
                    arb_opportunities.append({
                        "market_a": {"platform": a["platform"], "title": a["title"], "prob_yes": a["prob_yes"], "url": a["url"]},
                        "market_b": {"platform": b["platform"], "title": b["title"], "prob_yes": b["prob_yes"], "url": b["url"]},
                        "prob_diff": round(diff, 4),
                        "detected_at": NOW,
                    })
    arb_opportunities.sort(key=lambda x: x["prob_diff"], reverse=True)
    return arb_opportunities[:50]

# -- Main ------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== PredictPal Fetcher (Pro/Aggressive Mode) ===")
    poly, kalshi, manif, meta = fetch_polymarket(), fetch_kalshi(), fetch_manifold(), fetch_metaculus()
    all_markets = poly + kalshi + manif + meta
    pro_bets = fetch_trader_bets()
    arb = find_arbitrage(all_markets)
    os.makedirs("data", exist_ok=True)
    with open("data/markets.json", "w") as f:
        json.dump({"updated_at": NOW, "markets": all_markets}, f, indent=2)
    with open("data/pro_bets.json", "w") as f:
        json.dump({"updated_at": NOW, "bets": pro_bets}, f, indent=2)
    with open("data/arbitrage.json", "w") as f:
        json.dump({"updated_at": NOW, "opportunities": arb}, f, indent=2)
    print(f"Done. {len(all_markets)} markets. {len(arb)} arb ops found.")
