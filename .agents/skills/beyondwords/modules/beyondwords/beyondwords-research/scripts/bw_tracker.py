#!/usr/bin/env python3
"""bw_tracker.py — Beyondwords BSR history store (original). Free mini-Keepa.

SQLite append-only snapshot store. Daily snapshots rebuild BSR history for free;
the same DB also holds bw_sales.py calibration observations — the suite data loop.

Commands (JSON envelope out):
  add <ASIN> [--db tracker.db]                 live-fetch + store a snapshot
  add-snapshot <ASIN> '<json>' [--db ...]      store supplied numbers
      '{"bsr":12345,"price":4.99,"reviews":87,"title":"..."}'  (manual/paste path)
  report [--db ...] [--asin X]                 per-ASIN deltas + trend
  export [--db ...]                            watchlist: latest row per ASIN
"""
import json
import sqlite3
import sys
import time

TOOL = "bw_tracker"
VERSION = "1.0.0"

DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  day TEXT NOT NULL,
  asin TEXT NOT NULL,
  title TEXT,
  bsr INTEGER,
  price REAL,
  reviews INTEGER
);
CREATE INDEX IF NOT EXISTS ix_snap ON snapshots(asin, ts);
CREATE TABLE IF NOT EXISTS calibration (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  asin TEXT,
  bsr INTEGER NOT NULL,
  sales REAL NOT NULL
);
"""


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": not payload.get("blocked"), **payload}


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(DDL)
    return db


def insert_snapshot(path, asin, data):
    db = connect(path)
    db.execute("INSERT INTO snapshots (ts, day, asin, title, bsr, price, reviews) VALUES (?,?,?,?,?,?,?)",
               (time.time(), time.strftime("%Y-%m-%d"), asin,
                data.get("title"), data.get("bsr"), data.get("price"), data.get("reviews")))
    db.commit()
    db.close()
    return envelope({"stored": True, "asin": asin, "captured": data, "db": path})


def trend_report(path, only_asin=None):
    db = connect(path)
    sql = "SELECT asin, title, ts, bsr, price, reviews FROM snapshots"
    args = ()
    if only_asin:
        sql += " WHERE asin = ?"
        args = (only_asin,)
    rows = db.execute(sql + " ORDER BY asin, ts", args).fetchall()
    db.close()

    grouped = {}
    for asin, title, ts, bsr, price, reviews in rows:
        g = grouped.setdefault(asin, {"title": title, "points": []})
        g["title"] = title or g["title"]
        g["points"].append({"ts": ts, "bsr": bsr, "price": price, "reviews": reviews})

    report = []
    for asin, g in grouped.items():
        pts = g["points"]
        first, last = pts[0], pts[-1]
        row = {
            "asin": asin, "title": g["title"], "snapshotCount": len(pts),
            "first": {"day": time.strftime("%Y-%m-%d", time.localtime(first["ts"])), "bsr": first["bsr"]},
            "latest": {"day": time.strftime("%Y-%m-%d", time.localtime(last["ts"])),
                       "bsr": last["bsr"], "price": last["price"], "reviews": last["reviews"]},
        }
        if len(pts) > 1 and first["bsr"] and last["bsr"]:
            change = last["bsr"] - first["bsr"]
            row["bsrChange"] = change
            row["trend"] = "climbing" if change < 0 else ("slipping" if change > 0 else "flat")
            row["note"] = "lower BSR = more sales; a negative change means the book is selling better"
        report.append(row)
    return envelope({"tracked": len(report), "asins": report, "db": path})


def watchlist(path):
    db = connect(path)
    rows = db.execute(
        """SELECT s.asin, s.title, s.bsr, s.price, s.reviews, s.day FROM snapshots s
           JOIN (SELECT asin, MAX(ts) m FROM snapshots GROUP BY asin) t
             ON t.asin = s.asin AND t.m = s.ts
           ORDER BY s.bsr IS NULL, s.bsr ASC""").fetchall()
    db.close()
    return envelope({"watchlist": [
        {"asin": a, "title": t, "latestBsr": b, "latestPrice": p, "latestReviews": r, "asOf": d}
        for a, t, b, p, r, d in rows], "db": path})


def live_add(path, asin):
    import bw_amazon
    sess = bw_amazon.BrowserSession()
    sess.warm_up()
    data = bw_amazon.run_product(sess, asin)
    if data.get("blocked"):
        return envelope({"blocked": True,
                         "advice": "fetch blocked — read the numbers off the page and use add-snapshot"})
    return insert_snapshot(path, asin, data)


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    path = opt("--db", "tracker.db")
    cmd = argv[0]
    if cmd == "add":
        out = live_add(path, argv[1])
    elif cmd == "add-snapshot":
        out = insert_snapshot(path, argv[1], json.loads(argv[2]))
    elif cmd == "report":
        out = trend_report(path, opt("--asin"))
    elif cmd == "export":
        out = watchlist(path)
    else:
        raise SystemExit(f'unknown command "{cmd}" — add|add-snapshot|report|export')
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
