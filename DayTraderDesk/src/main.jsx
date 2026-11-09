import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Bell, Bookmark, CandlestickChart,
  ChevronDown, CircleHelp, Clock3, Command, Compass, Crosshair, ExternalLink, Eye,
  Gauge, LayoutDashboard, ListFilter, LoaderCircle, Plus, RefreshCw, Search, Shield,
  SlidersHorizontal, Sparkles, Target, TrendingDown, TrendingUp, Wallet, X,
} from 'lucide-react';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import './styles.css';

const INITIAL_WATCHLIST = ['SPY', 'QQQ', 'AAPL', 'NVDA', 'TSLA', 'MSFT', 'AMD', 'AMZN'];
const SETUP_NAMES = {
  '20-day closing-high breakout': '20D breakout',
  'bull flag': 'Bull flag',
  'reclaimed 20-day average': 'MA20 reclaim',
  'RSI oversold': 'Oversold',
  'oversold bounce': 'Oversold bounce',
};
const money = (n, digits = 2) => Number.isFinite(Number(n)) ? Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—';
const compact = (n) => !Number.isFinite(Number(n)) ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
const when = (s) => s ? new Date(s).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—';
const todayBrief = `${new Intl.DateTimeFormat('en-US', { weekday: 'long' }).format(new Date()).toUpperCase()} MARKET BRIEF`;

async function getJson(url, signal) {
  const res = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}

function IconButton({ title, onClick, children, className = '' }) {
  return <button className={`icon-button ${className}`} title={title} aria-label={title} onClick={onClick}>{children}</button>;
}

function Change({ value, compact: compactMode = false }) {
  const n = Number(value || 0);
  const up = n >= 0;
  return <span className={`change ${up ? 'positive' : 'negative'}`}>{up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}{compactMode ? `${Math.abs(n).toFixed(2)}%` : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`}</span>;
}

function App() {
  const [watchlist, setWatchlist] = useState(() => {
    try { return JSON.parse(localStorage.getItem('northstar-watchlist')) || INITIAL_WATCHLIST; }
    catch { return INITIAL_WATCHLIST; }
  });
  const [activeSymbol, setActiveSymbol] = useState('SPY');
  const [range, setRange] = useState('3mo');
  const [page, setPage] = useState('overview');
  const [quotes, setQuotes] = useState([]);
  const [history, setHistory] = useState(null);
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [risk, setRisk] = useState({ account: '25000', maxRisk: '125', entry: '', stop: '', target: '' });

  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [marketResult, chartResult] = await Promise.allSettled([
        getJson(`/api/market?symbols=${encodeURIComponent(watchlist.join(','))}`),
        getJson(`/api/history?symbols=${encodeURIComponent(activeSymbol)}&range=${range}`),
      ]);
      const messages = [];
      if (marketResult.status === 'fulfilled') {
        const market = marketResult.value;
        setQuotes(market.quotes || []);
        setLastUpdated(market.asOf || new Date().toISOString());
        if (market.missing?.length) messages.push(`No current history returned for ${market.missing.join(', ')}.`);
      } else messages.push(marketResult.reason.message || 'Market overview could not be loaded.');
      if (chartResult.status === 'fulfilled') setHistory(chartResult.value);
      else messages.push(chartResult.reason.message || 'Price history could not be loaded.');
      setError(messages.join(' '));
    } finally { setLoading(false); }
  }, [watchlist, activeSymbol, range]);

  const refreshScan = useCallback(async () => {
    setScanLoading(true);
    try { setScan(await getJson(`/api/scan?symbols=${encodeURIComponent(watchlist.join(','))}`)); }
    catch (e) { setScan({ error: e.message || 'Scanner could not reach the data provider.' }); }
    finally { setScanLoading(false); }
  }, [watchlist]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { localStorage.setItem('northstar-watchlist', JSON.stringify(watchlist)); }, [watchlist]);
  useEffect(() => { if (!scan && !scanLoading) refreshScan(); }, [scan, scanLoading, refreshScan]);

  const activeQuote = quotes.find((item) => item.symbol === activeSymbol) || history?.quote;
  const chartBars = history?.bars || [];
  const closes = chartBars.map((bar) => bar.close).filter(Number.isFinite);
  const hi = closes.length ? Math.max(...closes) : 0;
  const lo = closes.length ? Math.min(...closes) : 0;
  const maxRisk = Number(risk.maxRisk), entry = Number(risk.entry), stop = Number(risk.stop), target = Number(risk.target), account = Number(risk.account);
  const perShareRisk = entry - stop;
  const riskCappedShares = entry > stop && maxRisk > 0 ? Math.floor(maxRisk / perShareRisk) : 0;
  const accountCappedShares = entry > 0 && account > 0 ? Math.floor(Math.min(account * 0.75, 4000, account * 0.9) / entry) : 0;
  const shareCount = riskCappedShares > 0 && accountCappedShares > 0 ? Math.min(riskCappedShares, accountCappedShares) : 0;
  const positionCost = shareCount * entry;
  const lossAtStop = shareCount * (entry - stop);
  const rewardRisk = shareCount && target > entry ? (target - entry) / (entry - stop) : 0;

  const addTicker = (raw) => {
    const symbol = raw.toUpperCase().trim().replace(/\$/g, '');
    if (!/^[A-Z]{1,5}(?:[.-][A-Z]{1,2})?$/.test(symbol)) { setError('Enter a valid US stock or ETF ticker.'); return; }
    setWatchlist((prev) => prev.includes(symbol) ? prev : [...prev, symbol].slice(-20));
    setActiveSymbol(symbol); setSearchOpen(false); setSearchValue(''); setError('');
  };

  const pageTitle = page === 'overview' ? 'Market overview' : page === 'scanner' ? 'Setup scanner' : 'Risk planner';
  const setupRows = scan?.hits || [];
  const nav = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'scanner', label: 'Scanner', icon: Crosshair, badge: scan?.hits?.length },
    { id: 'risk', label: 'Risk planner', icon: Shield },
  ];

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><CandlestickChart size={19} /></div><div><b>northstar</b><span>MARKET DESK</span></div></div>
      <div className="workspace-switch"><div className="workspace-avatar">N</div><div className="workspace-copy"><b>Personal workspace</b><span>Research account</span></div><ChevronDown size={15} /></div>
      <div className="side-section-label">WORKSPACE</div>
      <nav className="primary-nav" aria-label="Main navigation">
        {nav.map(({ id, label, icon: Icon, badge }) => <button key={id} onClick={() => setPage(id)} className={`nav-link ${page === id ? 'selected' : ''}`}><Icon size={17} /><span>{label}</span>{badge > 0 && <i>{badge}</i>}</button>)}
      </nav>
      <div className="sidebar-watch-head"><span className="side-section-label">WATCHLIST</span><IconButton title="Add ticker" onClick={() => setSearchOpen(true)}><Plus size={16} /></IconButton></div>
      <div className="watch-items">
        {watchlist.map((sym) => {
          const q = quotes.find((x) => x.symbol === sym);
          return <button key={sym} className={`watch-item ${activeSymbol === sym ? 'active' : ''}`} onClick={() => { setActiveSymbol(sym); setPage('overview'); }}><span className="ticker-icon">{sym.slice(0, 1)}</span><span className="watch-name"><b>{sym}</b><small>{q?.name && q.name !== sym ? q.name : 'US listed'}</small></span><span className={`watch-price ${q?.changePct >= 0 ? 'positive' : 'negative'}`}>{q ? `${q.changePct >= 0 ? '+' : ''}${q.changePct.toFixed(2)}%` : '···'}</span></button>;
        })}
      </div>
      <div className="sidebar-bottom"><div className="data-status"><span className="status-dot" /><div><b>Public market data</b><small>Yahoo Finance · may be delayed</small></div></div><div className="sidebar-footer"><span>Paper research only</span><CircleHelp size={15} /></div></div>
    </aside>

    <main className="main-area">
      <header className="topbar">
        <div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><b>{pageTitle}</b></div>
        <div className="top-actions"><div className="market-pill"><span className="status-dot" />US equities <span className="market-time">· ET</span></div><IconButton title="Notifications"><Bell size={17} /></IconButton><div className="user-avatar">H</div></div>
      </header>
      <div className="content-wrap">
        <section className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" />{todayBrief}</div><h1>{pageTitle}<span className="heading-period">.</span></h1><p>{page === 'risk' ? 'Plan a position size before you consider a trade.' : page === 'scanner' ? 'Surface chart conditions from completed daily bars.' : 'A calmer view of the market, setups, and risk.'}</p></div><div className="heading-actions"><span className="updated-label"><Clock3 size={14} />{lastUpdated ? `Updated ${when(lastUpdated)}` : 'Waiting for data'}</span><button className="button secondary" onClick={() => { refresh(); if (page === 'scanner') refreshScan(); }} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''} />Refresh</button></div></section>

        <div className="source-banner"><div className="source-symbol"><Activity size={16} /></div><div><b>Live market context</b><span>Yahoo Finance public chart data · unofficial, may be delayed or unavailable</span></div><span className="source-tag">REAL DATA</span></div>
        {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={refresh}>Retry</button></div>}

        {page === 'overview' && <>
          <section className="market-strip" aria-label="Market indices">
            {['SPY', 'QQQ', 'DIA', 'IWM'].map((sym) => {
              const q = quotes.find((x) => x.symbol === sym);
              return <button className={`index-card ${activeSymbol === sym ? 'focus' : ''}`} key={sym} onClick={() => setActiveSymbol(sym)}><span className="index-label">{sym} <span className="index-kind">ETF</span></span><b className="index-value">{q ? money(q.price) : <span className="skeleton-text">······</span>}</b><span className="index-change">{q ? <Change value={q.changePct} /> : <span className="muted">Loading</span>}<small>{q?.exchange || 'Market proxy'}</small></span></button>;
            })}
          </section>

          <section className="dashboard-grid">
            <article className="panel chart-panel">
              <div className="panel-head chart-head"><div><div className="panel-kicker">PRICE ACTION</div><div className="asset-title"><div className="asset-avatar">{activeSymbol.slice(0, 1)}</div><div><h2>{activeSymbol}</h2><span>{activeQuote?.name || 'Loading instrument'} <i>·</i> {activeQuote?.exchange || 'US listing'}</span></div></div></div><div className="chart-head-right"><div className="chart-price">{activeQuote ? money(activeQuote.price) : '—'}{activeQuote && <Change value={activeQuote.changePct} />}</div><div className="range-select">{[['1mo','1M'],['3mo','3M'],['6mo','6M'],['1y','1Y']].map(([value,label]) => <button key={value} onClick={() => setRange(value)} className={range === value ? 'on' : ''}>{label}</button>)}</div></div></div>
              <div className="chart-meta"><span><i className="legend-dot" />Close</span><span>Range high <b>{closes.length ? money(hi) : '—'}</b></span><span>Range low <b>{closes.length ? money(lo) : '—'}</b></span></div>
              <div className="chart-wrap">{chartBars.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartBars} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}><defs><linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6ab49a" stopOpacity={0.2} /><stop offset="95%" stopColor="#6ab49a" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#222d3b" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} tick={{ fill: '#738096', fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={32} /><YAxis domain={['auto','auto']} orientation="right" tickFormatter={(v) => `$${Number(v).toFixed(0)}`} tick={{ fill: '#738096', fontSize: 11 }} axisLine={false} tickLine={false} width={50} /><Tooltip content={<ChartTooltip />} /><Area type="monotone" dataKey="close" stroke="#80c9ad" strokeWidth={2} fill="url(#priceFill)" activeDot={{ r: 4, strokeWidth: 0, fill: '#b2e6d2' }} isAnimationActive animationDuration={650} /></AreaChart></ResponsiveContainer> : <div className="chart-empty">{loading ? <><LoaderCircle className="spin" size={22} /><span>Loading observed price history…</span></> : <><CandlestickChart size={22} /><span>Price history isn’t available right now.</span><button className="text-button" onClick={refresh}>Try again</button></>}</div>}</div>
              <div className="chart-foot"><span>Daily close <i>·</i> {chartBars.length ? `${chartBars.length} observed sessions` : 'No bars loaded'}</span><span>Source: Yahoo Finance</span></div>
            </article>

            <article className="panel activity-panel"><div className="panel-head"><div><div className="panel-kicker">TODAY’S CONTEXT</div><h2>At a glance</h2></div><span className="panel-icon"><Gauge size={17} /></span></div><div className="context-list"><ContextRow label="Selected instrument" value={activeSymbol} icon={CandlestickChart} /><ContextRow label="Latest observed price" value={activeQuote ? money(activeQuote.price) : '—'} icon={Activity} /><ContextRow label="Latest bar" value={activeQuote?.lastBar ? new Date(activeQuote.lastBar).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'} icon={Clock3} /><ContextRow label="Session" value="US equities · ET" icon={Compass} /></div><div className="context-note"><div className="note-icon"><Eye size={15} /></div><p>Conditions describe historical chart patterns. They are not predictions and do not tell you whether to trade.</p></div><button className="panel-link" onClick={() => setPage('scanner')}>Review chart setups <ArrowRight size={15} /></button></article>
          </section>

          <section className="bottom-grid">
            <article className="panel watch-panel"><div className="panel-head"><div><div className="panel-kicker">YOUR UNIVERSE</div><h2>Watchlist</h2></div><button className="button subtle" onClick={() => setSearchOpen(true)}><Plus size={14} />Add symbol</button></div><div className="watch-table-wrap"><table className="watch-table"><thead><tr><th>INSTRUMENT</th><th>LAST PRICE</th><th>DAY CHANGE</th><th>EXCHANGE</th><th></th></tr></thead><tbody>{watchlist.map((sym) => { const q = quotes.find((x) => x.symbol === sym); return <tr key={sym} onClick={() => { setActiveSymbol(sym); setPage('overview'); }}><td><span className="table-symbol-icon">{sym[0]}</span><span className="table-symbol"><b>{sym}</b><small>{q?.name || 'US listed security'}</small></span></td><td className="mono">{q ? money(q.price) : '—'}</td><td>{q ? <Change value={q.changePct} /> : '—'}</td><td className="muted">{q?.exchange || '—'}</td><td><IconButton title={`Remove ${sym}`} onClick={(event) => { event.stopPropagation(); if (watchlist.length > 1) setWatchlist(watchlist.filter((x) => x !== sym)); }}>{<X size={15} />}</IconButton></td></tr>; })}</tbody></table></div><div className="table-footer"><span>{watchlist.length} symbols in your list</span><button className="text-button" onClick={() => setSearchOpen(true)}>Manage watchlist <ArrowRight size={13} /></button></div></article>
            <article className="panel setup-panel"><div className="panel-head"><div><div className="panel-kicker">RULE-BASED SCAN</div><h2>Chart setups</h2></div><IconButton title="Refresh scanner" onClick={refreshScan}><RefreshCw size={15} className={scanLoading ? 'spin' : ''} /></IconButton></div><p className="panel-description">Pattern conditions from completed daily bars in your watchlist.</p>{scan?.error ? <div className="inline-error">{scan.error}<button className="text-button" onClick={refreshScan}>Retry</button></div> : scanLoading && !scan ? <div className="scanner-empty"><LoaderCircle className="spin" size={19} /><span>Scanning observed history…</span></div> : setupRows.length ? <div className="setup-list">{setupRows.slice(0, 4).map((row) => <button className="setup-row" key={row.symbol} onClick={() => { setActiveSymbol(row.symbol); setPage('overview'); }}><span className="setup-symbol">{row.symbol}</span><span className="setup-tags">{row.setups.slice(0,2).map((tag) => <i key={tag}>{SETUP_NAMES[tag] || tag}</i>)}</span><span className="setup-rsi">RSI {row.rsi?.toFixed(0) || '—'}</span></button>)}</div> : <div className="scanner-empty"><div className="empty-mark"><ListFilter size={18} /></div><b>No matching setups found</b><span>The scan found no listed patterns in the available completed bars.</span></div>}<button className="panel-link" onClick={() => setPage('scanner')}>Open scanner <ArrowRight size={15} /></button></article>
          </section>
        </>}

        {page === 'scanner' && <section className="panel full-panel scanner-page"><div className="panel-head"><div><div className="panel-kicker">DAILY PRICE ACTION</div><h2>Watchlist scanner</h2></div><button className="button secondary" disabled={scanLoading} onClick={refreshScan}><RefreshCw size={14} className={scanLoading ? 'spin' : ''} />Scan again</button></div><p className="panel-description">Checks completed daily closes for five defined conditions. Current-session bars are excluded until the US cash session closes.</p><div className="scan-rules">{Object.values(SETUP_NAMES).map((name) => <span key={name}><span className="rule-dot" />{name}</span>)}</div>{scan?.error ? <ErrorState message={scan.error} retry={refreshScan} /> : scanLoading && !scan ? <div className="scanner-empty tall"><LoaderCircle className="spin" size={21} /><span>Loading observed market history…</span></div> : <><div className="table-caption">{scan?.scanned ?? '—'} symbols checked <span>Source: Yahoo Finance · not a recommendation</span></div>{setupRows.length ? <div className="watch-table-wrap"><table className="watch-table scan-table"><thead><tr><th>SYMBOL</th><th>LAST COMPLETED CLOSE</th><th>RSI (14)</th><th>OBSERVED PATTERN</th><th>BAR DATE</th></tr></thead><tbody>{setupRows.map((row) => <tr key={row.symbol} onClick={() => { setActiveSymbol(row.symbol); setPage('overview'); }}><td><span className="table-symbol-icon">{row.symbol[0]}</span><span className="table-symbol"><b>{row.symbol}</b><small>Daily bars</small></span></td><td className="mono">{money(row.price)}</td><td className="mono">{row.rsi?.toFixed(1) ?? '—'}</td><td><div className="setup-tags">{row.setups.map((tag) => <i key={tag}>{SETUP_NAMES[tag] || tag}</i>)}</div></td><td className="muted">{new Date(row.date).toLocaleDateString()}</td></tr>)}</tbody></table></div> : <div className="scanner-empty tall"><div className="empty-mark"><Search size={18} /></div><b>No setups matched this scan</b><span>That is a valid result. Try again later or adjust your watchlist.</span></div>}</>}</section>}

        {page === 'risk' && <section className="risk-layout"><article className="panel risk-form-panel"><div className="panel-kicker">PRE-TRADE CHECKLIST</div><h2>Plan the risk first.</h2><p className="panel-description">Estimate a share count from the maximum loss you choose. This tool does not create or send orders.</p><div className="risk-form"><MoneyInput label="Account value" prefix="$" value={risk.account} onChange={(v) => setRisk({ ...risk, account: v })} /><MoneyInput label="Maximum planned loss" prefix="$" value={risk.maxRisk} onChange={(v) => setRisk({ ...risk, maxRisk: v })} /><div className="form-divider" /><MoneyInput label="Entry price" prefix="$" value={risk.entry} placeholder="0.00" onChange={(v) => setRisk({ ...risk, entry: v })} /><MoneyInput label="Stop level" prefix="$" value={risk.stop} placeholder="0.00" onChange={(v) => setRisk({ ...risk, stop: v })} /><MoneyInput label="Target level (optional)" prefix="$" value={risk.target} placeholder="0.00" onChange={(v) => setRisk({ ...risk, target: v })} /></div><div className="risk-caution"><Shield size={15} /><span>A stop price does not guarantee an execution price. Gaps and fast markets can increase losses.</span></div></article><article className="panel risk-result-panel"><div className="panel-head"><div><div className="panel-kicker">POSITION ESTIMATE</div><h2>Risk summary</h2></div><span className="panel-icon"><Target size={17} /></span></div>{shareCount > 0 ? <><div className="share-estimate"><strong>{shareCount.toLocaleString()}</strong><span>shares at planned entry</span></div><div className="risk-metric-list"><RiskMetric label="Position value" value={money(positionCost)} /><RiskMetric label="Estimated loss at stop" value={money(lossAtStop)} warn={lossAtStop > maxRisk} /><RiskMetric label="Account exposure" value={`${account > 0 ? (positionCost/account*100).toFixed(1) : '0.0'}%`} /><RiskMetric label="Potential reward / risk" value={target > entry && entry > stop ? `${rewardRisk.toFixed(2)}×` : 'Add a target'} good={rewardRisk >= 1} /></div><div className="risk-result-note"><span className="status-dot" />Uses whole-share rounding and your stated loss limit. Fees, slippage, liquidity, taxes, and price gaps are excluded.</div></> : <div className="risk-empty"><div className="empty-mark"><Shield size={19} /></div><b>Enter an entry and a stop</b><span>Your estimate appears here once the risk inputs are valid.</span></div>}<div className="no-order"><span className="lock-dot" />Planning only · no broker connection · no orders sent</div></article></section>}

        <footer className="disclaimer"><div className="disclaimer-icon"><CircleHelp size={15} /></div><div><b>Educational research only</b><p>Market data is provided by Yahoo Finance, an unofficial source that may be delayed, revised, rate-limited, or unavailable. Chart setups are historical conditions, not forecasts or trade recommendations. Day trading can result in substantial losses.</p></div><a href="https://finance.yahoo.com/" target="_blank" rel="noreferrer">Data provider <ExternalLink size={12} /></a></footer>
      </div>
    </main>

    {searchOpen && <div className="modal-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) setSearchOpen(false); }}><div className="search-modal" role="dialog" aria-modal="true" aria-label="Add symbol"><div className="search-modal-head"><div><div className="panel-kicker">WATCHLIST</div><h2>Add a symbol</h2></div><IconButton title="Close" onClick={() => setSearchOpen(false)}><X size={18} /></IconButton></div><form onSubmit={(e) => { e.preventDefault(); addTicker(searchValue); }}><div className="search-input-wrap"><Search size={16} /><input autoFocus value={searchValue} onChange={(e) => setSearchValue(e.target.value)} placeholder="Type a US ticker, like NVDA" maxLength={8} /><button type="submit" disabled={!searchValue.trim()}><Plus size={14} />Add</button></div></form><p className="modal-hint">This app requests market data for the symbol from Yahoo Finance. Unsupported symbols are reported as unavailable; no sample prices are shown.</p><div className="quick-add"><span>POPULAR</span>{['AAPL','NVDA','TSLA','AMD'].filter((sym) => !watchlist.includes(sym)).map((sym) => <button key={sym} onClick={() => addTicker(sym)}>{sym}<Plus size={12} /></button>)}</div></div></div>}
  </div>;
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return <div className="chart-tooltip"><b>{money(p.close)}</b><span>{new Date(p.date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</span></div>;
}
function ContextRow({ label, value, icon: Icon }) { return <div className="context-row"><span className="context-icon"><Icon size={15} /></span><span className="context-label">{label}</span><b>{value}</b></div>; }
function MoneyInput({ label, prefix, value, onChange, placeholder }) { return <label className="money-input"><span>{label}</span><div><i>{prefix}</i><input type="number" min="0" step="any" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} /></div></label>; }
function RiskMetric({ label, value, warn, good }) { return <div className="risk-metric"><span>{label}</span><b className={warn ? 'negative' : good ? 'positive' : ''}>{value}</b></div>; }
function ErrorState({ message, retry }) { return <div className="error-state"><div className="empty-mark"><CircleHelp size={18} /></div><b>Market data unavailable</b><span>{message}</span><button className="button secondary" onClick={retry}>Retry</button></div>; }

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
