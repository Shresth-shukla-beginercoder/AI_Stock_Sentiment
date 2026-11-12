"""Probe Twelve Data symbol formats for HKEX/KRX vs a known-good US symbol.

Goal: distinguish 'wrong symbol string' from 'plan/coverage gate'.
Bounded: a handful of quote calls per candidate. Never prints the key.
"""
import os
import time
import httpx

REPO = r"C:\Users\shres\OneDrive\Desktop\AI - Stock_Sentiment -Agent"
os.chdir(REPO)


def load_env():
    env = {}
    with open(os.path.join(REPO, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


env = load_env()
key = env.get("TWELVE_DATA_API_KEY", "")
client = httpx.Client(timeout=30)

# Candidate symbol strings per exchange. If ANY returns bars for a real HK/KR
# company, the issue is the exact string the app currently emits. If NONE work
# (all 404 "invalid symbol") while AAPL works, it is a plan/coverage gate.
candidates = {
    "HKEX (Tencent 0700)": ["0700.HK", "700.HK", "0700", "TCEHY"],
    "KRX (Samsung 005930)": ["005930.KS", "005930", "SSNLF"],
    "US control (AAPL)": ["AAPL"],
}

for label, syms in candidates.items():
    print(f"== {label} ==")
    for sym in syms:
        try:
            r = client.get("https://api.twelvedata.com/quote",
                           params={"symbol": sym, "apikey": key})
            b = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            status = b.get("status", r.status_code)
            msg = str(b.get("message", ""))[:70]
            price = b.get("close")
            ok = status == 200 and price not in (None, "", "0")
            mark = "OK " if ok else ("ERR" if str(status) in ("401","403") else "404" if r.status_code==404 else "   ")
            print(f"   [{mark}] {sym:12} HTTP {r.status_code} status={status} "
                  f"{msg} close={price}")
            time.sleep(8)  # stay under the 8 credits/min free-plan rate
        except Exception as e:
            print(f"   [EXC] {sym:12} {type(e).__name__}: {str(e)[:80]}")
    print()
print("DONE")
