
// ── PredictPal App ──────────────────────────────────────────────────────────
const DATA_BASE = "./data/";
let allMarkets = [], allTraders = [], allArb = [], allTrades = [], bankroll = {};
let activeTab = "markets";
let activePlatformFilter = "all";

// ── Fetch helpers ────────────────────────────────────────────────────────────
async function fetchJSON(path) {
  try {
    const r = await fetch(path + "?t=" + Date.now());
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

async function loadAllData() {
  const [mData, tData, aData, trData, brData] = await Promise.all([
    fetchJSON(DATA_BASE + "markets.json"),
    fetchJSON(DATA_BASE + "traders.json"),
    fetchJSON(DATA_BASE + "arbitrage.json"),
    fetchJSON(DATA_BASE + "trades.json"),
    fetchJSON(DATA_BASE + "bankroll.json"),
  ]);

  allMarkets = mData?.markets || sampleMarkets();
  allTraders = tData?.traders || sampleTraders();
  allArb     = aData?.opportunities || [];
  allTrades  = trData?.trades || [];
  bankroll   = brData || { balance: 100000, peak: 100000, total_trades: 0 };

  const updated = mData?.updated_at || new Date().toISOString();
  document.getElementById("last-updated").textContent =
    "Updated: " + new Date(updated).toLocaleTimeString();

  renderAll();
}

// ── Nav ──────────────────────────────────────────────────────────────────────
document.querySelectorAll(".nav-tab").forEach(btn => {
  btn.addEventListener("click", () => {
    activeTab = btn.dataset.tab;
    document.querySelectorAll(".nav-tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    document.getElementById("page-" + activeTab).classList.add("active");
    renderAll();
  });
});

// ── Platform filters ─────────────────────────────────────────────────────────
document.querySelectorAll(".filter-btn[data-platform]").forEach(btn => {
  btn.addEventListener("click", () => {
    activePlatformFilter = btn.dataset.platform;
    document.querySelectorAll(".filter-btn[data-platform]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderMarkets();
  });
});

// ── Stat cards ───────────────────────────────────────────────────────────────
function updateStats() {
  const totalMarkets = allMarkets.length;
  const platforms = new Set(allMarkets.map(m => m.platform)).size;
  const openTrades = allTrades.filter(t => t.status === "open").length;
  const pnl = allTrades.reduce((s, t) => s + (t.pnl || 0), 0);

  setEl("stat-markets",  totalMarkets);
  setEl("stat-platforms", platforms);
  setEl("stat-arb",      allArb.length);
  setEl("stat-trades",   openTrades);
  setEl("stat-balance",  "$" + bankroll.balance?.toLocaleString("en-US", {maximumFractionDigits: 0}) || "$100,000");
  setEl("stat-pnl",      (pnl >= 0 ? "+" : "") + "$" + pnl.toFixed(0));

  const pnlEl = document.getElementById("stat-pnl");
  if (pnlEl) pnlEl.className = "value " + (pnl >= 0 ? "text-green" : "text-red");
}

function setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── Market Cards ─────────────────────────────────────────────────────────────
function platformBadgeClass(p) {
  return "badge-" + p.toLowerCase().replace(/\s+/g, "");
}

function renderMarkets() {
  const grid = document.getElementById("markets-grid");
  if (!grid) return;

  let filtered = allMarkets;
  if (activePlatformFilter !== "all") {
    filtered = allMarkets.filter(m => m.platform.toLowerCase() === activePlatformFilter);
  }

  const search = document.getElementById("market-search")?.value?.toLowerCase() || "";
  if (search) filtered = filtered.filter(m => m.title.toLowerCase().includes(search));

  if (!filtered.length) {
    grid.innerHTML = '<div class="empty-state">No markets found.</div>';
    return;
  }

  grid.innerHTML = filtered.slice(0, 60).map(m => {
    const pct = Math.round(m.prob_yes * 100);
    const vol = formatVol(m.volume);
    return `
    <a class="market-card" href="${m.url}" target="_blank" rel="noopener">
      <span class="platform-badge ${platformBadgeClass(m.platform)}">${m.platform}</span>
      <div class="title">${escHtml(m.title)}</div>
      <div class="prob-bar-wrap">
        <div class="prob-bar-bg"><div class="prob-bar-fill" style="width:${pct}%"></div></div>
        <div class="prob-labels">
          <span class="text-green">YES ${pct}%</span>
          <span class="text-red">NO ${100-pct}%</span>
        </div>
      </div>
      <div class="market-meta">
        <span>Vol: ${vol}</span>
        <span>${m.category || "general"}</span>
      </div>
    </a>`;
  }).join("");
}

// ── Arbitrage ────────────────────────────────────────────────────────────────
function renderArb() {
  const grid = document.getElementById("arb-grid");
  if (!grid) return;
  if (!allArb.length) {
    grid.innerHTML = '<div class="empty-state">No arbitrage opportunities detected right now.</div>';
    return;
  }
  grid.innerHTML = allArb.map(op => {
    const diffPct = (op.prob_diff * 100).toFixed(1);
    return `
    <div class="arb-card">
      <div class="arb-diff">⚡ ${diffPct}% price gap detected</div>
      <div class="arb-row">
        <span class="arb-platform">${op.market_a.platform}</span>
        <span class="arb-prob text-green">${Math.round(op.market_a.prob_yes*100)}% YES</span>
        <a href="${op.market_a.url}" target="_blank" style="font-size:.72rem;color:var(--accent)">Open ↗</a>
      </div>
      <div class="arb-row">
        <span class="arb-platform">${op.market_b.platform}</span>
        <span class="arb-prob text-red">${Math.round(op.market_b.prob_yes*100)}% YES</span>
        <a href="${op.market_b.url}" target="_blank" style="font-size:.72rem;color:var(--accent)">Open ↗</a>
      </div>
      <div style="font-size:.72rem;color:var(--text2);margin-top:8px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis"
           title="${escHtml(op.market_a.title)}">${escHtml(op.market_a.title.substring(0,60))}…</div>
    </div>`;
  }).join("");
}

// ── Traders ──────────────────────────────────────────────────────────────────
function renderTraders() {
  const grid = document.getElementById("traders-grid");
  if (!grid) return;
  if (!allTraders.length) {
    grid.innerHTML = '<div class="empty-state">Loading trader data...</div>';
    return;
  }
  grid.innerHTML = allTraders.map((t, i) => {
    const profit = t.profit ?? 0;
    const addr = t.address ? t.address.substring(0,6) + "…" + t.address.substring(t.address.length-4) : "Unknown";
    return `
    <div class="trader-card">
      <div class="trader-name">#${i+1} ${escHtml(t.name || "Anonymous")}</div>
      <div class="wallet">${addr}</div>
      <div class="trader-stats">
        <div class="trader-stat">
          <div class="ts-label">Profit</div>
          <div class="ts-val ${profit >= 0 ? 'text-green' : 'text-red'}">$${Math.abs(profit).toLocaleString()}</div>
        </div>
        <div class="trader-stat">
          <div class="ts-label">Volume</div>
          <div class="ts-val">${formatVol(t.volume)}</div>
        </div>
        <div class="trader-stat">
          <div class="ts-label">Markets</div>
          <div class="ts-val">${t.markets_traded ?? "–"}</div>
        </div>
        <div class="trader-stat">
          <div class="ts-label">Platform</div>
          <div class="ts-val text-accent">Poly</div>
        </div>
      </div>
    </div>`;
  }).join("");
}

// ── Trades table ──────────────────────────────────────────────────────────────
function renderTrades() {
  const tbody = document.getElementById("trades-tbody");
  if (!tbody) return;

  // Update bankroll banner
  setEl("br-balance",  "$" + (bankroll.balance || 100000).toLocaleString("en-US", {maximumFractionDigits: 0}));
  setEl("br-starting", "$100,000");
  setEl("br-peak",     "$" + (bankroll.peak || 100000).toLocaleString("en-US", {maximumFractionDigits: 0}));
  setEl("br-open",     allTrades.filter(t => t.status === "open").length);

  const totalPnl = allTrades.reduce((s, t) => s + (t.pnl || 0), 0);
  const pnlEl = document.getElementById("br-pnl");
  if (pnlEl) {
    pnlEl.textContent = (totalPnl >= 0 ? "+" : "") + "$" + totalPnl.toFixed(0);
    pnlEl.className   = "br-val " + (totalPnl >= 0 ? "text-green" : "text-red");
  }

  if (!allTrades.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No trades yet. The engine will find opportunities on next data refresh.</td></tr>';
    return;
  }

  tbody.innerHTML = allTrades.slice().reverse().slice(0, 50).map(t => {
    const pnlTxt = t.pnl != null ? (t.pnl >= 0 ? "+" : "") + "$" + t.pnl.toFixed(0) : "–";
    const pnlCls = t.pnl == null ? "" : t.pnl >= 0 ? "text-green" : "text-red";
    const edgePct = (t.edge * 100).toFixed(1);
    const statusBadge = `<span class="badge-${t.status}">${t.status}</span>`;
    return `
    <tr>
      <td>${statusBadge}</td>
      <td><a href="${t.url}" target="_blank" style="color:var(--accent)">${escHtml(t.title?.substring(0,45) || "–")}…</a></td>
      <td><span class="platform-badge ${platformBadgeClass(t.platform)}">${t.platform}</span></td>
      <td style="font-weight:600">${t.side}</td>
      <td>${Math.round(t.market_prob * 100)}% → ${Math.round(t.true_prob_estimate * 100)}%</td>
      <td class="text-yellow">${edgePct}%</td>
      <td>$${t.bet_amount?.toLocaleString()}</td>
      <td class="${pnlCls}">${pnlTxt}</td>
    </tr>`;
  }).join("");
}

// ── Render all ───────────────────────────────────────────────────────────────
function renderAll() {
  updateStats();
  renderMarkets();
  renderArb();
  renderTraders();
  renderTrades();
}

// ── Search ───────────────────────────────────────────────────────────────────
document.getElementById("market-search")?.addEventListener("input", renderMarkets);

// ── Utils ─────────────────────────────────────────────────────────────────────
function formatVol(v) {
  if (!v) return "–";
  if (v >= 1_000_000) return "$" + (v / 1_000_000).toFixed(1) + "M";
  if (v >= 1_000)     return "$" + (v / 1_000).toFixed(1) + "K";
  return "$" + v.toFixed(0);
}
function escHtml(s) {
  if (!s) return "";
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── Sample data (shown when data/ files don't exist yet) ─────────────────────
function sampleMarkets() {
  return [
    { id:"s1", platform:"Polymarket", title:"Will the NBA Finals go to 7 games?", prob_yes:0.42, prob_no:0.58, volume:320000, url:"https://polymarket.com", category:"sports" },
    { id:"s2", platform:"Kalshi",     title:"Will the NBA Finals go to 7 games?", prob_yes:0.38, prob_no:0.62, volume:85000, url:"https://kalshi.com", category:"sports" },
    { id:"s3", platform:"Manifold",   title:"Will the Fed cut rates before June?", prob_yes:0.61, prob_no:0.39, volume:12000, url:"https://manifold.markets", category:"economics" },
    { id:"s4", platform:"Metaculus",  title:"Will the Fed cut rates before June?", prob_yes:0.55, prob_no:0.45, volume:4200, url:"https://metaculus.com", category:"economics" },
    { id:"s5", platform:"Polymarket", title:"Will Bitcoin exceed $120k in 2026?", prob_yes:0.33, prob_no:0.67, volume:2100000, url:"https://polymarket.com", category:"crypto" },
    { id:"s6", platform:"Kalshi",     title:"Will US unemployment exceed 5%?", prob_yes:0.22, prob_no:0.78, volume:190000, url:"https://kalshi.com", category:"economics" },
  ];
}
function sampleTraders() {
  return [
    { address:"0xabc123def456", name:"SharpBettor.eth", profit:142000, volume:1800000, markets_traded:87 },
    { address:"0x9f8e7d6c5b4a", name:"EarlyEdge",       profit:98500,  volume:750000,  markets_traded:54 },
    { address:"0x1122334455aa", name:"Anonymous",        profit:71200,  volume:430000,  markets_traded:31 },
  ];
}

// ── Init ─────────────────────────────────────────────────────────────────────
loadAllData();
setInterval(loadAllData, 5 * 60 * 1000); // auto-refresh every 5 min
