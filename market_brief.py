# -*- coding: utf-8 -*-
"""
매일 아침 미국 증시 브리핑 페이지를 만드는 스크립트.
실행하면 site/index.html 이 만들어집니다.

※ 코딩을 몰라도 아래 '설정' 부분만 고치면 됩니다.
"""
import os
import io
import json
import html
import datetime as dt
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

KST = ZoneInfo("Asia/Seoul")

# =====================================================================
#  설정 — 여기만 고치면 됩니다
# =====================================================================

# 주요 지표: (야후 파이낸스 티커, 화면에 보일 이름, 단위)
# 단위: "$" = 앞에 달러 표시, "%" = 뒤에 % 표시, "원" = 뒤에 원 표시, "" = 숫자만
INDICATORS = [
    ("^TNX",    "미국 10년물 금리", "%"),
    ("^VIX",    "VIX 변동성지수",  ""),
    ("CL=F",    "WTI 원유",        "$"),
    ("^IXIC",   "나스닥 종합",     ""),
    ("^GSPC",   "S&P 500",         ""),
    ("GC=F",    "금 (Gold)",       "$"),
    ("BTC-USD", "비트코인",        "$"),
    ("KRW=X",   "원/달러 환율",    "원"),
]

# 관심 종목: 원하는 종목으로 자유롭게 바꾸세요 (티커는 finance.yahoo.com 에서 검색)
WATCHLIST = [
    ("NVDA", "엔비디아", "$"),
    ("AMD",  "AMD",      "$"),
    ("MU",   "마이크론", "$"),
    ("TSM",  "TSMC",     "$"),
    ("PANW", "팔로알토", "$"),
    ("LITE", "루멘텀",   "$"),
]

# 뉴스 검색어 (구글 뉴스). 'when:1d' = 최근 하루
HEADLINE_QUERY = "뉴욕증시 when:1d"
KOREA_IMPACT_QUERIES = ["코스피 전망 when:1d", "환율 유가 증시 when:1d"]
KOREA_NEWS_COUNT = 3

# 신고가 카드를 시가총액 순으로 몇 개 보여줄지
TOP_HIGHS = 6

# (선택) Claude API 키가 있으면 회사 이름·설명을 한국어로 바꿔줍니다
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# =====================================================================

SECTOR_KO = {
    "Technology": "기술", "Energy": "에너지", "Healthcare": "헬스케어",
    "Financial Services": "금융", "Industrials": "산업재",
    "Communication Services": "커뮤니케이션", "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재", "Utilities": "유틸리티",
    "Real Estate": "부동산", "Basic Materials": "소재",
}
WEEKDAY_KO = "월화수목금토일"
UA = {"User-Agent": "Mozilla/5.0 (market-brief)"}


def log(*a):
    print("[brief]", *a, flush=True)


# --------------------------- 가격 데이터 ---------------------------

def fetch_closes(tickers, period):
    df = yf.download(list(tickers), period=period, interval="1d",
                     auto_adjust=True, progress=False, threads=True)
    closes = df["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(list(tickers)[0])
    return closes


def _past_value(s, days):
    target = s.index[-1] - pd.Timedelta(days=days)
    past = s[s.index <= target]
    return None if past.empty else float(past.iloc[-1])


def make_indicator(s, ticker, name, unit):
    s = s.dropna()
    if len(s) < 2:
        return None
    last, prev = float(s.iloc[-1]), float(s.iloc[-2])
    is_bp = ticker == "^TNX"   # 금리는 bp(0.01%p) 단위로 변화 표시
    out = dict(ticker=ticker, name=name, unit=unit, is_bp=is_bp,
               date=s.index[-1].strftime("%m/%d"), price=last,
               chg=(last - prev) * (100 if is_bp else 1),
               pct=(last / prev - 1) * 100 if prev else 0.0)
    for key, days in (("r1w", 7), ("r1m", 30), ("r3m", 91)):
        p = _past_value(s, days)
        if p is None:
            out[key] = None
        else:
            out[key] = (last - p) * 100 if is_bp else (last / p - 1) * 100
    spark = s[s.index >= s.index[-1] - pd.Timedelta(days=91)]
    out["spark"] = [float(v) for v in spark.values]
    return out


def collect_indicators(items):
    closes = fetch_closes([t for t, _, _ in items], "6mo")
    result = []
    for t, name, unit in items:
        if t in closes.columns:
            ind = make_indicator(closes[t], t, name, unit)
            if ind:
                result.append(ind)
        else:
            log("데이터 없음:", t)
    return result


# --------------------------- Put/Call ---------------------------

def put_call_ratio(ticker="SPY", expirations=3):
    """SPY 옵션 거래량 기준 풋/콜 비율 (가까운 만기 3개 합산)"""
    tk = yf.Ticker(ticker)
    puts = calls = 0.0
    for e in tk.options[:expirations]:
        ch = tk.option_chain(e)
        puts += float(ch.puts["volume"].fillna(0).sum())
        calls += float(ch.calls["volume"].fillna(0).sum())
    return puts / calls if calls else None


# --------------------------- 뉴스 ---------------------------

def google_news(query, n=5):
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
           + "&hl=ko&gl=KR&ceid=KR:ko")
    req = urllib.request.Request(url, headers=UA)
    root = ET.fromstring(urllib.request.urlopen(req, timeout=20).read())
    items = []
    for it in root.iter("item"):
        title = it.findtext("title", "") or ""
        src = it.findtext("source", "") or ""
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            t = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        except Exception:
            t = None
        items.append(dict(title=title.strip(), link=it.findtext("link", ""),
                          source=src, time=t))
        if len(items) >= n:
            break
    return items


# --------------------------- 신고가 스캔 ---------------------------

def get_universe():
    """S&P500 + 나스닥100 종목 목록 (위키백과)"""
    tickers = set()
    pages = {
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies": ("Symbol",),
        "https://en.wikipedia.org/wiki/Nasdaq-100": ("Ticker", "Symbol"),
    }
    for url, cols in pages.items():
        try:
            r = requests.get(url, headers=UA, timeout=30)
            for tbl in pd.read_html(io.StringIO(r.text)):
                col = next((c for c in cols if c in tbl.columns), None)
                if col:
                    tickers.update(str(x).replace(".", "-").strip()
                                   for x in tbl[col].dropna())
                    break
        except Exception as e:
            log("종목 목록 실패:", url, e)
    return sorted(t for t in tickers if t and t.isascii())


def _info(t):
    try:
        return t, yf.Ticker(t).info or {}
    except Exception:
        return t, {}


def scan_new_highs(universe):
    closes = fetch_closes(universe, "1y")
    latest = closes.index.max()
    scanned, highs = 0, []
    for t in closes.columns:
        s = closes[t].dropna()
        if len(s) < 200 or s.index[-1] != latest:
            continue
        scanned += 1
        if s.iloc[-1] >= s.max() * 0.9999:
            highs.append(t)
    log(f"신고가 {len(highs)} / {scanned}")

    with ThreadPoolExecutor(max_workers=4) as ex:
        infos = dict(ex.map(_info, highs[:150]))

    sectors = {}
    for t in highs:
        sec = SECTOR_KO.get(infos.get(t, {}).get("sector"), "기타")
        sectors[sec] = sectors.get(sec, 0) + 1

    ranked = sorted(highs, key=lambda t: infos.get(t, {}).get("marketCap") or 0,
                    reverse=True)[:TOP_HIGHS]
    cards = []
    for t in ranked:
        info, s = infos.get(t, {}), closes[t].dropna()
        last = float(s.iloc[-1])
        six = s[s.index >= s.index[-1] - pd.Timedelta(days=182)]
        target = info.get("targetMeanPrice")
        summary = (info.get("longBusinessSummary") or "").split(". ")[0]
        cards.append(dict(
            ticker=t,
            name=info.get("shortName") or t,
            sector=SECTOR_KO.get(info.get("sector"), info.get("sector") or ""),
            desc=summary[:70] + ("…" if len(summary) > 70 else ""),
            summary_full=(info.get("longBusinessSummary") or "")[:400],
            price=last,
            pct=(last / float(s.iloc[-2]) - 1) * 100,
            spark=[float(v) for v in six.values],
            r6m=(last / float(six.iloc[0]) - 1) * 100,
            vs_prev=(last / float(s.iloc[:-1].max()) - 1) * 100,
            mcap=info.get("marketCap"),
            pe=info.get("trailingPE"), fpe=info.get("forwardPE"),
            pb=info.get("priceToBook"),
            rev=(info["revenueGrowth"] * 100) if info.get("revenueGrowth") is not None else None,
            target_gap=(target / last - 1) * 100 if target else None,
        ))
    return dict(count=len(highs), scanned=scanned,
                sectors=sorted(sectors.items(), key=lambda x: -x[1]),
                cards=cards)


def korean_names(cards):
    """ANTHROPIC_API_KEY 가 설정돼 있으면 회사명·설명을 한국어로"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not cards:
        return
    listing = "\n".join(f"{c['ticker']} | {c['name']} | {c['summary_full']}" for c in cards)
    prompt = ("다음 미국 상장사들에 대해 한국 투자자용 한국어 회사명과 25자 이내 사업 설명을 "
              "JSON으로만 답해. 형식: {\"TICKER\": {\"name\": \"...\", \"desc\": \"...\"}}\n\n"
              + listing)
    body = json.dumps({"model": CLAUDE_MODEL, "max_tokens": 1500,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        text = json.loads(urllib.request.urlopen(req, timeout=60).read())["content"][0]["text"]
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        for c in cards:
            ko = data.get(c["ticker"], {})
            c["name"] = ko.get("name") or c["name"]
            c["desc"] = ko.get("desc") or c["desc"]
    except Exception as e:
        log("한국어 변환 실패(무시하고 진행):", e)


# --------------------------- 모으기 ---------------------------

def collect():
    data = dict(generated=dt.datetime.now(KST), headline=None, chips=[],
                pcr=None, korea_news=[], indicators=[], watch=[], highs=None)
    try:
        data["indicators"] = collect_indicators(INDICATORS)
    except Exception as e:
        log("지표 실패:", e)
    try:
        data["watch"] = collect_indicators(WATCHLIST)
    except Exception as e:
        log("관심종목 실패:", e)
    by_t = {i["ticker"]: i for i in data["indicators"]}
    for t, label in (("^IXIC", "나스닥"), ("^GSPC", "S&P500")):
        if t in by_t:
            data["chips"].append((label, by_t[t]["pct"]))
    data["market_date"] = by_t.get("^GSPC", {}).get("date")
    try:
        news = google_news(HEADLINE_QUERY, 1)
        data["headline"] = news[0] if news else None
    except Exception as e:
        log("헤드라인 실패:", e)
    seen = set()
    for q in KOREA_IMPACT_QUERIES:
        try:
            for n in google_news(q, 5):
                if n["title"] not in seen and len(data["korea_news"]) < KOREA_NEWS_COUNT:
                    seen.add(n["title"])
                    data["korea_news"].append(n)
        except Exception as e:
            log("뉴스 실패:", q, e)
    try:
        data["pcr"] = put_call_ratio()
    except Exception as e:
        log("Put/Call 실패:", e)
    try:
        uni = get_universe()
        if uni:
            data["highs"] = scan_new_highs(uni)
            korean_names(data["highs"]["cards"])
    except Exception as e:
        log("신고가 스캔 실패:", e)
    return data


# --------------------------- 화면 만들기 ---------------------------

UP, DOWN, FLAT = "#e0312b", "#2563eb", "#8a8f98"


def color(v):
    if v is None or abs(v) < 1e-9:
        return FLAT
    return UP if v > 0 else DOWN


def arrow(v):
    return "▲" if v and v > 0 else ("▼" if v and v < 0 else "–")


def num(v, d=2):
    return "-" if v is None else f"{v:,.{d}f}"


def signed(v, d=2, suffix="%"):
    return "-" if v is None else f"{v:+,.{d}f}{suffix}"


def price_text(v, unit, is_bp=False):
    d = 3 if is_bp else 2
    if unit == "$":
        return f'<span class="unit">$</span>{num(v, d)}'
    if unit in ("%", "원"):
        return f'{num(v, d)}<span class="unit"> {unit}</span>'
    return num(v, d)


def spark_svg(vals, col, w=120, h=36):
    if not vals or len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1
    n = len(vals)
    pts = " ".join(f"{i / (n - 1) * w:.1f},{h - 2 - (v - mn) / rng * (h - 4):.1f}"
                   for i, v in enumerate(vals))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<polygon points="0,{h} {pts} {w},{h}" fill="{col}" fill-opacity=".1"/>'
            f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6" '
            f'vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>')


def e(s):
    return html.escape(str(s or ""))


def news_time(t):
    return t.strftime("%m/%d %H:%M") if t else ""


def tile(i):
    bp = i["is_bp"]
    chg_txt = f'{i["chg"]:+.1f}bp' if bp else f'{abs(i["chg"]):,.2f}'
    unit_r = "bp" if bp else "%"
    rets = "".join(
        f'<div><span>{lab}</span><b style="color:{color(i[k])}">'
        f'{signed(i[k], 1 if bp else 2, unit_r)}</b></div>'
        for lab, k in (("1주", "r1w"), ("1개월", "r1m"), ("3개월", "r3m")))
    return f"""
    <div class="tile">
      <div class="t-name">{e(i["name"])}</div>
      <div class="t-sub">{e(i["ticker"])} · {i["date"]}</div>
      <div class="t-price">{price_text(i["price"], i["unit"], bp)}</div>
      <div class="t-chg" style="color:{color(i["pct"])}">{arrow(i["pct"])} {chg_txt} ({signed(i["pct"])})</div>
      {spark_svg(i["spark"], color(i["pct"]))}
      <div class="rets">{rets}</div>
    </div>"""


def fmt_mcap(v):
    if not v:
        return "-"
    return f"${v / 1e12:.2f}T" if v >= 1e12 else f"${v / 1e9:,.0f}B"


def fmt_mult(v, d=1):
    if v is None:
        return "-"
    return "500배+" if v >= 500 else f"{v:,.{d}f}배"


def high_card(c):
    rows = [("시총", fmt_mcap(c["mcap"]), None), ("PER", fmt_mult(c["pe"]), None),
            ("선행 PER", fmt_mult(c["fpe"]), None), ("PBR", fmt_mult(c["pb"]), None),
            ("매출성장", signed(c["rev"], 0), c["rev"]),
            ("목표가 괴리", signed(c["target_gap"], 0), c["target_gap"])]
    rows_html = "".join(
        f'<div class="row"><span>{k}</span><b{"" if cv is None else f" style=\"color:{color(cv)}\""}>{v}</b></div>'
        for k, v, cv in rows)
    return f"""
    <div class="hcard">
      <div class="h-name">{e(c["name"])}</div>
      <div class="t-sub">{e(c["ticker"])} · {e(c["sector"])}</div>
      <div class="h-desc">{e(c["desc"])}</div>
      <div class="h-price" style="color:{color(c["pct"])}">{num(c["price"])}</div>
      <div class="t-chg" style="color:{color(c["pct"])}">{arrow(c["pct"])} {abs(c["pct"]):.2f}%</div>
      {spark_svg(c["spark"], color(c["pct"]), 160, 48)}
      <div class="h-meta">6개월 <b style="color:{color(c["r6m"])}">{signed(c["r6m"], 0)}</b> · 전고점 <b style="color:{color(c["vs_prev"])}">{signed(c["vs_prev"], 1)}</b></div>
      <div class="rows">{rows_html}</div>
    </div>"""


CSS = """
:root{--bg:#f2f3f5;--card:#fff;--ink:#16181d;--sub:#7b808a;--line:#eceef1;--chip:#f3f4f6}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#1a1d23;--ink:#eef0f3;--sub:#9198a3;--line:#2a2e36;--chip:#252930}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:16px 14px 48px;display:flex;flex-direction:column;gap:12px}
.hero{background:linear-gradient(120deg,#ffb020,#ff8a00);color:#fff;border-radius:16px;padding:16px 18px}
.hero small{font-size:11px;letter-spacing:.12em;opacity:.85;font-weight:700}
.hero h1{font-size:22px;margin:4px 0 2px;letter-spacing:-.02em}
.hero p{font-size:12px;opacity:.9}
.card{background:var(--card);border-radius:16px;padding:16px 18px}
.card h2{font-size:16px;margin-bottom:12px;letter-spacing:-.01em}
.head-news{border-left:4px solid #ff9a00}
.head-news a{color:var(--ink);text-decoration:none;font-size:20px;font-weight:800;line-height:1.35;letter-spacing:-.02em}
.meta{color:var(--sub);font-size:12px;margin-top:6px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.chip{background:var(--chip);border-radius:8px;padding:5px 9px;font-size:13px;font-weight:600}
.pcr{display:flex;justify-content:space-between;align-items:center}
.pcr .v{font-size:28px;font-weight:800}
.badge{display:inline-block;background:#ffb020;color:#fff;border-radius:999px;padding:4px 12px;font-size:13px;font-weight:700;margin-bottom:12px}
.knews{list-style:none;display:flex;flex-direction:column;gap:12px}
.knews li{display:flex;gap:10px}
.knews .n{flex:none;width:22px;height:22px;border-radius:50%;background:#ff9a00;color:#fff;font-size:12px;font-weight:800;display:grid;place-items:center;margin-top:2px}
.knews a{color:var(--ink);text-decoration:none;font-weight:700;font-size:15px;line-height:1.4}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
@media (max-width:560px){.grid{grid-template-columns:repeat(2,1fr)}}
.tile{border:1px solid var(--line);border-radius:12px;padding:10px;min-width:0}
.t-name{font-weight:700;font-size:13px}
.t-sub{color:var(--sub);font-size:11px;margin-top:1px}
.t-price{font-size:19px;font-weight:800;margin-top:6px;letter-spacing:-.02em;white-space:nowrap}
.unit{font-size:12px;font-weight:600;color:var(--sub)}
.t-chg{font-size:12px;font-weight:600;margin-top:2px}
.spark{display:block;width:100%;height:36px;margin:6px 0}
.rets{display:grid;grid-template-columns:repeat(3,1fr);font-size:10.5px;text-align:center;border-top:1px solid var(--line);padding-top:6px}
.rets span{display:block;color:var(--sub)}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.stat{border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.stat span{color:var(--sub);font-size:12px}
.stat b{display:block;font-size:24px;margin-top:4px}
.hgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media (max-width:420px){.hgrid{grid-template-columns:1fr}}
.hcard{background:var(--chip);border-radius:14px;padding:14px;min-width:0}
.h-name{font-size:18px;font-weight:800;color:#16a34a}
.h-desc{font-size:13px;margin-top:6px;line-height:1.4}
.h-price{font-size:26px;font-weight:800;margin-top:8px}
.hcard .spark{height:48px}
.h-meta{font-size:12px;color:var(--sub)}
.rows{margin-top:8px;border-top:1px solid var(--line);padding-top:6px}
.row{display:flex;justify-content:space-between;font-size:13px;padding:3px 0}
.row span{color:var(--sub)}
.foot{color:var(--sub);font-size:11px;text-align:center;line-height:1.6}
"""


def render(d):
    gen = d["generated"]
    md = d.get("market_date")
    if md:
        m, day = map(int, md.split("/"))
        year = gen.year if m <= gen.month else gen.year - 1
        mdate = dt.date(year, m, day)
        title = f"{mdate.year % 100}년 {m}월 {day}일 미국 데일리 마켓"
    else:
        title = "미국 데일리 마켓"
    sub = f"{gen:%Y-%m-%d}({WEEKDAY_KO[gen.weekday()]}) {gen:%H:%M} KST 기준"

    parts = [f'<div class="hero"><small>DAILY US MARKET</small><h1>{title}</h1><p>{sub}</p></div>']

    h = d.get("headline")
    if h or d["chips"]:
        chips = "".join(f'<span class="chip">{e(n)} <span style="color:{color(v)}">{signed(v)}</span></span>'
                        for n, v in d["chips"])
        head = (f'<a href="{e(h["link"])}" target="_blank" rel="noopener">{e(h["title"])}</a>'
                f'<div class="meta">{e(h["source"])} · {news_time(h["time"])}</div>') if h else ""
        parts.append(f'<div class="card head-news">{head}<div class="chips">{chips}</div></div>')

    if d.get("pcr") is not None:
        p = d["pcr"]
        state = "탐욕(콜 우세)" if p < 0.6 else ("공포(풋 우세)" if p > 1.0 else "보통")
        parts.append(f'<div class="card pcr"><div><b>Put/Call</b><div class="meta" style="margin:2px 0 0">SPY 옵션 거래량 · 정상 범위 0.6~1.0 · {state}</div></div><div class="v">{p:.2f}</div></div>')

    if d["korea_news"]:
        lis = "".join(
            f'<li><span class="n">{k}</span><div><a href="{e(n["link"])}" target="_blank" rel="noopener">{e(n["title"])}</a>'
            f'<div class="meta">{e(n["source"])} · {news_time(n["time"])}</div></div></li>'
            for k, n in enumerate(d["korea_news"], 1))
        parts.append(f'<div class="card"><span class="badge">오늘 한국 시장 영향</span><ol class="knews">{lis}</ol></div>')

    if d["indicators"]:
        parts.append('<div class="card"><h2>주요 지표</h2><div class="grid">'
                     + "".join(tile(i) for i in d["indicators"]) + "</div></div>")
    if d["watch"]:
        parts.append('<div class="card"><h2>관심 종목</h2><div class="grid">'
                     + "".join(tile(i) for i in d["watch"]) + "</div></div>")

    hi = d.get("highs")
    if hi:
        ratio = hi["count"] / hi["scanned"] * 100 if hi["scanned"] else 0
        secs = "".join(f'<span class="chip">{e(s)} <b>{n}</b></span>' for s, n in hi["sectors"])
        parts.append(
            f'<div class="card"><h2>신고가 요약 <span class="meta" style="font-weight:400">· 종가 기준 1년 최고가</span></h2>'
            f'<div class="stats"><div class="stat"><span>신고가 종목</span><b style="color:{UP}">{hi["count"]}</b></div>'
            f'<div class="stat"><span>검색 대상</span><b>{hi["scanned"]}</b></div>'
            f'<div class="stat"><span>신고가 비율</span><b>{ratio:.1f}%</b></div></div>'
            f'<div class="chips">{secs}</div></div>')
        if hi["cards"]:
            parts.append(f'<div class="card"><h2>시총 상위 신고가</h2><div class="hgrid">'
                         + "".join(high_card(c) for c in hi["cards"]) + "</div></div>")

    parts.append('<p class="foot">데이터: Yahoo Finance · Google News · 투자 판단의 책임은 본인에게 있습니다.<br>'
                 f'자동 생성 {gen:%Y-%m-%d %H:%M} KST</p>')

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{CSS}</style></head>
<body><main class="wrap">{"".join(parts)}</main></body></html>"""


def main():
    data = collect()
    os.makedirs("site", exist_ok=True)
    with open("site/index.html", "w", encoding="utf-8") as f:
        f.write(render(data))
    log("완료 → site/index.html")


if __name__ == "__main__":
    main()
