"""Per-date configuration for the day pipeline. DATE=YYYY-MM-DD in the environment (UTC calendar day)."""
import os, datetime, pathlib
DATE = os.environ.get("DATE", "2026-08-01")
_d = datetime.datetime.strptime(DATE, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
W0 = int(_d.timestamp()); NEXT = (_d + datetime.timedelta(days=1)).strftime("%Y-%m-%d"); PREV = (_d - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
WIN_START_US = W0 * 1_000_000; WIN_END_US = WIN_START_US + 86_400_000_000
DAYROOT = pathlib.Path(__file__).resolve().parent.parent / DATE
RAWB, RAWT, NORM, BOOKS = DAYROOT / "raw/binance", DAYROOT / "raw/tardis", DAYROOT / "normalized", DAYROOT / "books"
for p in (RAWB, RAWT, NORM, BOOKS): p.mkdir(parents=True, exist_ok=True)
TARDIS_Y, TARDIS_M, TARDIS_D = DATE[:4], DATE[5:7], DATE[8:10]
MARKETS_JSON = DAYROOT / f"btc5m_markets_{DATE}.json"
LADDERS = DAYROOT / f"polymarket_btc5m_{DATE}_books.parquet"
