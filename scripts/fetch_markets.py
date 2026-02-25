"""
PredictPal Market Data Fetcher
Pulls data from Polymarket, Kalshi, Manifold, and Metaculus.
Saves normalized JSON to /data/ for the frontend to read.
"""
import requests, json, time, os, re
from datetime import datetime, timezone

HEADERS = {"User-Agent": "PredictPal/1.0"}
NOW = datetime.now(timezone.utc).isoformat()

# ── helpers ────────────────────────────────────────────────────────────────────
def safe_get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  [WARN] {url} attempt {i+1} failed: {e}")
            time.sleep(2)
    return None

def norm(platform, title, prob_yes, volume, url, end_date=None, category=None, market_id=None):
    """Return a standardised market object."""
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

# ── Polymarket ──────────────────────────────────────────────────────────────────
def fetch_polymarket(limit=300):
    markets = []
    for offset in range(0, limit, 100):
        data = safe_get("https://gamma-api.polymarket.com/markets", params={
            "limit": 100, "offset": offset, "active": "true", "closed": "false",
            "_order": "volume24hr", "_sort": "desc"
        })
        if not data:
            break
        items = data if isinstance(data, list) else data.get("markets", [])
        for m in items:
            try:
                prices = json.loads(m.get("outcomePrices", "[0.5,0.5]"))
                outcomes = json.loads(m.get("outcomes", '["Yes","No"]'))
                yes_idx = next((i for i, o in enumerate(outcomes) if o.lower() == "yes"), 0)
                prob = float(prices[yes_idx])
                markets.append(norm(
                    platform="Polymarket",
                    title=m.get("question", m.get("title", "")),
                    prob_yes=prob,
                    volume=m.get("volumeNum", m.get("volume", 0)),
                    url=f"https://polymarket.com/event/{m.get('slug', '')}",
                    end_date=m.get("endDate"),
                    category=m.get("category", "general"),
                    market_id=m.get("id"),
                ))
            except Exception as e:
                print(f"  [Polymarket parse error] {e}")
        if len(items) < 100:
            break
        time.sleep(0.5)
    print(f"  Polymarket: {len(markets)} markets")
    return markets[:limit]

# ── Kalshi ──────────────────────────────────────────────────────────────────────
def fetch_kalshi(limit=300):
    markets = []
    cursor = None
    while len(markets) < limit:
        params = {"limit": 100, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        data = safe_get("https://api.elections.kalshi.com/trade-api/v2/markets", params=params)
        if not data:
            break
        batch = data.get("markets", [])
        for m in batch:
            try:
                yes_price = m.get("yes_price", 50) / 100.0
                markets.append(norm(
                    platform="Kalshi",
                    title=m.get("title", ""),
                    prob_yes=yes_price,
                    volume=m.get("volume", 0),
                    url=f"https://kalshi.com/markets/{m.get('event_ticker','').lower()}",
                    end_date=m.get("close_time"),
                    category=m.get("category", "general"),
                    market_id=m.get("ticker"),
                ))
            except Exception as e:
                print(f"  [Kalshi parse error] {e}")
        cursor = data.get("cursor")
        if not cursor or len(batch) < 100:
            break
        time.sleep(0.5)
    print(f"  Kalshi: {len(markets)} markets")
    return markets[:limit]

# ── Manifold ────────────────────────────────────────────────────────────────────
def fetch_manifold(limit=300):
    markets = []
    before = None
    while len(markets) < limit:
        params = {"limit": 100, "sort": "liquidity"}
        if before:
            params["before"] = before
        data = safe_get("https://api.manifold.markets/v0/markets", params=params)
        if not data:
            break
        batch = data if isinstance(data, list) else []
        for m in batch:
            try:
                if m.get("outcomeType") != "BINARY":
                    continue
                prob = m.get("probability", 0.5)
                markets.append(norm(
                    platform="Manifold",
                    title=m.get("question", ""),
                    prob_yes=prob,
                    volume=m.get("volume", 0),
                    url=m.get("url", ""),
                    end_date=m.get("closeTime"),
                    category=m.get("category", "general"),
                    market_id=m.get("id"),
                ))
            except Exception as e:
                print(f"  [Manifold parse error] {e}")
        if len(batch) < 100:
            break
        before = batch[-1].get("id") if batch else None
        if not before:
            break
        time.sleep(0.5)
    print(f"  Manifold: {len(markets)} markets")
    return markets[:limit]

# ── Metaculus ───────────────────────────────────────────────────────────────────
def fetch_metaculus(limit=300):
    markets = []
    url = "https://www.metaculus.com/api2/questions/"
    while len(markets) < limit and url:
        data = safe_get(url, params={
            "limit": 100, "order_by": "-activity", "status": "open", "type": "forecast"
        } if "?" not in url else None)
        if not data:
            break
        for m in data.get("results", []):
            try:
                cp = m.get("community_prediction", {})
                prob = cp.get("full", {}).get("q2", 0.5) if cp else 0.5
                if prob is None:
                    prob = 0.5
                markets.append(norm(
                    platform="Metaculus",
                    title=m.get("title", ""),
                    prob_yes=prob,
                    volume=m.get("number_of_predictions", 0),
                    url=f"https://www.metaculus.com{m.get('page_url', '')}",
                    end_date=m.get("resolve_time"),
                    category=m.get("categories", [{}])[0].get("name", "general") if m.get("categories") else "general",
                    market_id=str(m.get("id")),
                ))
            except Exception as e:
                print(f"  [Metaculus parse error] {e}")
        url = data.get("next")
        if not url or len(data.get("results", [])) < 100:
            break
        time.sleep(0.5)
    print(f"  Metaculus: {len(markets)} markets")
    return markets[:limit]

# ── Polymarket top traders ──────────────────────────────────────────────────────
def fetch_top_traders(limit=20):
    traders = []
    data = safe_get("https://data-api.polymarket.com/activity", params={
        "limit": limit, "offset": 0
    })
    if not data:
        return traders
    items = data if isinstance(data, list) else data.get("results", [])
    for t in items[:limit]:
        try:
            traders.append({
                "address": t.get("proxyWallet", t.get("address", "")),
                "name": t.get("name", "Anonymous"),
                "profit": t.get("profit", 0),
                "volume": t.get("volumeTraded", 0),
                "markets_traded": t.get("marketsTraded", 0),
                "fetched_at": NOW,
            })
        except Exception as e:
            print(f"  [Trader parse error] {e}")
    print(f"  Traders: {len(traders)} fetched")
    return traders

# ── Improved Arbitrage Detector ────────────────────────────────────────────────
def extract_core_topic(title):
    """Extract key entities from title for better matching."""
    # Remove common question words and punctuation
    title = title.lower()
    title = re.sub(r'[?.,!]', '', title)
    # Remove common prediction market phrases
    stopwords = {'will', 'be', 'at', 'least', 'more', 'than', 'less', 'by', 'before', 
                 'after', 'in', 'on', 'of', 'the', 'a', 'an', 'to', 'for', 'is', 'as',
                 'and', 'or', 'not', 'end', 'close', 'above', 'below', 'over', 'under',
                 'reach', 'hit', 'have', 'has', 'people', 'number', 'total'}
    words = [w for w in title.split() if w not in stopwords and len(w) > 2]
    return set(words)

def find_arbitrage(all_markets, threshold=0.03):
    """
    Improved arbitrage detector using:
    1. Core topic extraction (entity-based matching)
    2. Keyword overlap with stopword removal
    3. Lower threshold (3%) since we have more markets
    """
    arb_opportunities = []
    
    # Pre-compute core topics for all markets
    market_topics = [(m, extract_core_topic(m["title"])) for m in all_markets]
    
    for i, (a, topics_a) in enumerate(market_topics):
        for j in range(i+1, len(market_topics)):
            b, topics_b = market_topics[j]
            
            # Skip same platform
            if a["platform"] == b["platform"]:
                continue
            
            # Skip if very low volume on both (likely stale)
            if a.get("volume", 0) < 100 and b.get("volume", 0) < 100:
                continue
            
            # Calculate keyword overlap
            if not topics_a or not topics_b:
                continue
            overlap = len(topics_a & topics_b) / max(len(topics_a | topics_b), 1)
            
            # Lower threshold: 30% topic overlap (was 50%)
            if overlap >= 0.30:
                diff = abs(a["prob_yes"] - b["prob_yes"])
                if diff >= threshold:
                    arb_opportunities.append({
                        "market_a": {"platform": a["platform"], "title": a["title"], 
                                     "prob_yes": a["prob_yes"], "url": a["url"]},
                        "market_b": {"platform": b["platform"], "title": b["title"], 
                                     "prob_yes": b["prob_yes"], "url": b["url"]},
                        "prob_diff": round(diff, 4),
                        "topic_overlap": round(overlap, 3),
                        "detected_at": NOW,
                    })
    
    arb_opportunities.sort(key=lambda x: x["prob_diff"], reverse=True)
    print(f"  Arbitrage: {len(arb_opportunities)} opportunities found")
    return arb_opportunities[:30]  # return top 30 (was 20)

# ── Main ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== PredictPal Fetcher ===")
    poly   = fetch_polymarket()
    kalshi = fetch_kalshi()
    manif  = fetch_manifold()
    meta   = fetch_metaculus()
    traders = fetch_top_traders()
    all_markets = poly + kalshi + manif + meta
    arb = find_arbitrage(all_markets)
    os.makedirs("data", exist_ok=True)
    with open("data/markets.json", "w") as f:
        json.dump({"updated_at": NOW, "markets": all_markets}, f, indent=2)
    with open("data/traders.json", "w") as f:
        json.dump({"updated_at": NOW, "traders": traders}, f, indent=2)
    with open("data/arbitrage.json", "w") as f:
        json.dump({"updated_at": NOW, "opportunities": arb}, f, indent=2)
    print(f"\nDone. {len(all_markets)} total markets saved.")
