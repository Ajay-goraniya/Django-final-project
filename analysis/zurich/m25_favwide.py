#!/usr/bin/env python3
"""M25 - FAV-wide (favourite ask 0.55-0.90) against base FAV (0.65-0.85). READ-ONLY.

Prereg: analysis/v/maker2/PREREG_M25_FAVWIDE.md. Only the band changes; the window (60-180), the
calm cut (<0.304 on poly_fav's definition) and the fill model are the shadow's own. The fill model
is CALLED, not reimplemented - S._fav_fill and S._fav_pnl are the functions the live shadow uses,
which is the only way the two arms are comparable on the same footing.
"""
import sys, datetime as dt
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S

BASE, WIDE = S.FAV_BAND, (0.55, 0.90)
BAR = 60
T = lambda *a: int(dt.datetime(*a, tzinfo=dt.UTC).timestamp())
NOW = int(dt.datetime.now(dt.UTC).timestamp())

S.ALL52, S.STRICT = None, None
S.FAV_BK = S._fav_books()
S.FAV_BN1 = S._bn_1s()
cand, vo, nk = S.load_candles()


def pick(rows, band):
    fv = sorted((r for r in rows
                 if S.FAV_SEC[0] <= r['sec'] <= S.FAV_SEC[1]
                 and r['own'] > r['opp']
                 and band[0] <= r['own'] <= band[1]),
                key=lambda r: r['ts'])
    return dict(fv[0]) if fv else None


def trade(ep, r0):
    """The shadow's own partial arrival fill. Returns (pnl, got, ask, ts) or None if no fill."""
    fd = S._fav_fill(cand[ep], r0)
    pnl = S._fav_pnl(fd, r0['win'])
    return dict(pnl=float(pnl), got=float(fd['got']), vwap=fd['vwap'], px=fd['px'],
                ask=float(r0['own']), ts=int(r0['ts']), sec=int(r0['sec']), win=r0['win'])


REC = {}
for ep in sorted(cand):
    if ep not in vo: continue
    v = S._vol_bn(S.FAV_BN1, ep)
    if v is None or v >= S.FAV_CUT_LOW: continue        # the frozen calm gate, both arms
    try:
        rows = S.build_rows(cand[ep], ep, vo[ep], nk)
    except Exception:
        continue
    b, w = pick(rows, BASE), pick(rows, WIDE)
    REC[ep] = dict(base=trade(ep, b) if b else None, wide=trade(ep, w) if w else None, vol=v)

L = [f'M25 - FAV-WIDE {WIDE} vs BASE FAV {BASE}. READ-ONLY, nothing deployed. '
     f'{dt.datetime.now(dt.UTC):%F %T} UTC',
     'Only the band differs. Window 60-180, calm < 0.304, one buy per candle, and the fill model is',
     "the shadow's own _fav_fill / _fav_pnl (arrival +500 ms, real recorded ask, exact fee, $10),",
     'called rather than reimplemented. "Fill" means got > 0 shares.',
     f'calm candles replayed: {len(REC)}', '']


def tot(eps, key):
    t = [REC[e][key] for e in eps if REC[e][key] and REC[e][key]['got'] > 0]
    pnl = sum(x['pnl'] for x in t)
    return len(t), pnl, (pnl / (10.0 * len(t)) if t else 0.0)


def block(title, a, b):
    eps = [e for e in sorted(REC) if a <= e < b]
    out = ['', f'== {title}  ({len(eps)} calm candles)',
           f'   {"arm":10s} {"fills":>5s} {"pnl $@10":>9s} {"per $1":>8s} {"H1 pnl":>8s} {"H2 pnl":>8s}  flag']
    half = eps[:(len(eps) + 1) // 2], eps[(len(eps) + 1) // 2:]
    res = {}
    for name, key in (('base FAV', 'base'), ('FAV-wide', 'wide')):
        n, pnl, per = tot(eps, key)
        h1 = tot(half[0], key)[1]; h2 = tot(half[1], key)[1]
        res[key] = dict(n=n, pnl=pnl, per=per, h1=h1, h2=h2)
        out.append(f'   {name:10s} {n:5d} {pnl:+9.2f} {per:+8.4f} {h1:+8.2f} {h2:+8.2f}  '
                   f'{"INSUFFICIENT (<60)" if n < BAR else ""}')
    out.append(f'   diff wide-base: {res["wide"]["pnl"]-res["base"]["pnl"]:+.2f} $  '
               f'{res["wide"]["per"]-res["base"]["per"]:+.4f} per $1')
    return out, res, eps


fwd, hist = (T(2026, 9, 29), NOW), (T(2026, 9, 24), T(2026, 9, 29))
o, RF, EF = block('(a) FORWARD 09-29 00:00 .. now', *fwd); L += o
o, RH, EH = block('(b) HISTORY 09-24 .. 28', *hist); L += o
o, RT, ET = block('(bonus) TODAY 10-02 only', T(2026, 10, 2), NOW); L += o

# ---- paired ------------------------------------------------------------------------------------
def paired(eps, title):
    same = extra = diff = 0
    dp_w = dp_b = 0.0
    ex_p = 0.0
    rows = []
    for e in eps:
        b, w = REC[e]['base'], REC[e]['wide']
        bf = b and b['got'] > 0; wf = w and w['got'] > 0
        if not wf and not bf: continue
        if wf and not bf:
            extra += 1; ex_p += w['pnl']; rows.append((e, 'extra', None, w))
        elif wf and bf:
            if abs(w['ask'] - b['ask']) < 1e-9 and w['ts'] == b['ts']:
                same += 1
            else:
                diff += 1; dp_w += w['pnl']; dp_b += b['pnl']; rows.append((e, 'diff', b, w))
    n_dis = extra + diff
    out = ['', f'== PAIRED, {title}: only candles where the two DISAGREE carry information',
           f'   identical trade (same entry): {same}',
           f'   EXTRA - wide trades, base does not: {extra}, their pnl {ex_p:+.2f}'
           f'{"  INSUFFICIENT (<60)" if extra < BAR else ""}',
           f'   DIFFERENT entry, both trade: {diff}, wide {dp_w:+.2f} vs base {dp_b:+.2f} '
           f'(wide-base {dp_w-dp_b:+.2f}){"  INSUFFICIENT (<60)" if diff < BAR else ""}',
           f'   total discordant {n_dis}; FAV-wide net on them {ex_p+dp_w-dp_b:+.2f}'
           f'{"  INSUFFICIENT (<60)" if n_dis < BAR else ""}']
    if diff:
        aw = sum(r[3]['ask'] for r in rows if r[1] == 'diff') / diff
        ab = sum(r[2]['ask'] for r in rows if r[1] == 'diff') / diff
        sw = sum(r[3]['sec'] for r in rows if r[1] == 'diff') / diff
        sb = sum(r[2]['sec'] for r in rows if r[1] == 'diff') / diff
        out.append(f'   on the DIFFERENT ones wide buys at avg ask {aw:.3f} sec {sw:.0f} against base '
                   f'{ab:.3f} sec {sb:.0f} - the prereg mechanism, measured forward')
    return out, dict(extra=extra, ex_p=ex_p, diff=diff, dw=dp_w, db=dp_b, n=n_dis)

o, PF = paired(EF, 'FORWARD'); L += o
o, PH = paired(EH, 'HISTORY 09-24..28'); L += o
o, PT = paired(ET, 'TODAY 10-02'); L += o

# ---- per day -----------------------------------------------------------------------------------
L += ['', '== PER DAY, every day shown',
      f'   {"day":8s} {"candles":>7s} {"base n":>6s} {"base $":>8s} {"wide n":>6s} {"wide $":>8s} {"wide-base":>9s}']
days = sorted({dt.datetime.fromtimestamp(e, dt.UTC).strftime('%m-%d') for e in REC})
for d in days:
    eps = [e for e in sorted(REC) if dt.datetime.fromtimestamp(e, dt.UTC).strftime('%m-%d') == d]
    nb, pb, _ = tot(eps, 'base'); nw, pw, _ = tot(eps, 'wide')
    L.append(f'   {d:8s} {len(eps):7d} {nb:6d} {pb:+8.2f} {nw:6d} {pw:+8.2f} {pw-pb:+9.2f}')

# ---- the prereg's four checks ------------------------------------------------------------------
c1 = RF['wide']['pnl'] > 0 and RF['wide']['h1'] > 0 and RF['wide']['h2'] > 0 and RF['wide']['n'] >= BAR
c2 = RF['wide']['pnl'] > RF['base']['pnl'] and RF['wide']['per'] > RF['base']['per']
c3net = PF['ex_p'] + PF['dw'] - PF['db']
c3 = c3net > 0 and PF['n'] >= BAR
L += ['', '== THE PREREG\'S FOUR CHECKS, on the FORWARD period',
      f'   1 FAV-wide pnl > 0, both halves > 0, fills >= 60: pnl {RF["wide"]["pnl"]:+.2f}, '
      f'halves {RF["wide"]["h1"]:+.2f}/{RF["wide"]["h2"]:+.2f}, fills {RF["wide"]["n"]} -> '
      f'{"PASS" if c1 else "FAIL"}',
      f'   2 beats base in $ AND per $1: {RF["wide"]["pnl"]:+.2f} vs {RF["base"]["pnl"]:+.2f} and '
      f'{RF["wide"]["per"]:+.4f} vs {RF["base"]["per"]:+.4f} -> {"PASS" if c2 else "FAIL"}',
      f'   3 paired discordant trades pnl > 0 on n >= 60: net {c3net:+.2f} on n {PF["n"]} -> '
      f'{"PASS" if c3 else ("INSUFFICIENT" if c3net > 0 and PF["n"] < BAR else "FAIL")}',
      f'   4 per day reported, no day hidden: PASS ({len(days)} days above)',
      '', f'   OVERALL: {"PASS" if (c1 and c2 and c3) else "FAIL"} - per the prereg, a failure leaves '
      f'base FAV as the reference and nothing is proposed.']
print('\n'.join(L))
