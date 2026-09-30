#!/usr/bin/env python3
"""Tests for arm PFAV's scorer, run BEFORE it writes any forward row."""
import sys, unittest
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
import pfav

EP=1790000000; UP='TOKUP'; DN='TOKDN'
def book(sec_bid):           # {sec: (up_bid, dn_bid)}
    return [(EP+s, u, d) for s,(u,d) in sorted(sec_bid.items())]
def tape(rows):              # (sec, asset, price, size, is_taker[, side]) with sec in CANDLE seconds
    return [(EP+s+pfav.LAG, a, p, z, t, (r[5] if len(r)>5 else 'BUY')) for r in rows for s,a,p,z,t in [r[:5]]]

class T(unittest.TestCase):
    def test_no_post_when_bid_outside_band(self):
        b=book({s:(0.55,0.44) for s in range(60,181)})
        self.assertEqual(pfav.score(EP,b,[],(UP,DN),UP,{}),{})
    def test_posts_on_first_in_band_second(self):
        b=book({**{s:(0.55,0.44) for s in range(60,90)},**{s:(0.70,0.29) for s in range(90,181)}})
        r=pfav.score(EP,b,tape([(95,UP,0.70,20,0)]),(UP,DN),UP,{})
        self.assertEqual(r['PFAV'][2],95)            # filled at the print second
        self.assertEqual(r['PFAV'][1],0.70)          # at the posted bid
        self.assertEqual(r['PFAV'][3],1)
    def test_rejoin_takes_the_higher_bid(self):
        b=book({**{s:(0.62,0.37) for s in range(60,100)},**{s:(0.74,0.25) for s in range(100,181)}})
        r=pfav.score(EP,b,tape([(150,UP,0.74,20,0)]),(UP,DN),UP,{})
        self.assertEqual(r['PFAV'][1],0.74,'should re-join the risen best bid')
    def test_needs_enough_shares(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        r=pfav.score(EP,b,tape([(100,UP,0.70,13,0)]),(UP,DN),UP,{})
        self.assertEqual(r['PFAV'][3],0,'13 shares must NOT fill the >=14 arm')
        self.assertEqual(r['PFAV50'][3],0)
        r2=pfav.score(EP,b,tape([(100,UP,0.70,14,0)]),(UP,DN),UP,{})
        self.assertEqual(r2['PFAV'][3],1)
        self.assertEqual(r2['PFAV50'][3],0,'14 shares must not fill the >=50 arm')
    def test_mint_mirror_fills(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        r=pfav.score(EP,b,tape([(110,DN,0.31,30,0)]),(UP,DN),UP,{})
        self.assertEqual(r['PFAV'][3],1,'other token at >= 1-bid (0.30) must fill via the mint mirror')
        r2=pfav.score(EP,b,tape([(110,DN,0.29,30,0)]),(UP,DN),UP,{})
        self.assertEqual(r2['PFAV'][3],0,'below 1-bid must NOT fill')
    def test_taker_prints_do_not_fill_the_passive_arm(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        r=pfav.score(EP,b,tape([(100,UP,0.70,100,1)]),(UP,DN),UP,{})
        self.assertEqual(r['PFAV'][3],0,'a TAKER print must not fill a passive post')
    def test_window_is_respected(self):
        b=book({s:(0.70,0.29) for s in range(0,300)})
        r=pfav.score(EP,b,tape([(40,UP,0.70,50,0),(200,UP,0.70,50,0)]),(UP,DN),UP,{})
        self.assertEqual(r['PFAV'][3],0,'prints outside 60-180 must not fill')
    def test_pnl_has_no_fee_and_loss_is_full_stake(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        w=pfav.score(EP,b,tape([(100,UP,0.70,20,0)]),(UP,DN),UP,{})['PFAV']
        self.assertAlmostEqual(w[5], 10/0.70-10, places=9)   # no fee on a maker fill
        l=pfav.score(EP,b,tape([(100,UP,0.70,20,0)]),(UP,DN),DN,{})['PFAV']
        self.assertAlmostEqual(l[5], -10.0, places=9)
    def test_taker_arm_pays_fee(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        r=pfav.score(EP,b,tape([(100,UP,0.70,20,0),(105,UP,0.72,5,1)]),(UP,DN),UP,{})
        self.assertIn('PFAV_taker',r)
        p=0.72; self.assertAlmostEqual(r['PFAV_taker'][5], 10/(p+0.07*p*(1-p))-10, places=9)

    # ---- PFAV_THRU: a print AT our bid must NOT fill it; only strictly through counts ----
    def test_thru_needs_strictly_below_our_bid(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        r=pfav.score(EP,b,tape([(100,UP,0.70,50,0)]),(UP,DN),UP,{})
        self.assertEqual(r['PFAV'][3],1,'a print AT the bid fills the TOUCH arm')
        self.assertEqual(r['PFAV_THRU'][3],0,'a print AT the bid must NOT fill the THRU arm')
        r2=pfav.score(EP,b,tape([(100,UP,0.69,50,0)]),(UP,DN),UP,{})
        self.assertEqual(r2['PFAV_THRU'][3],1,'strictly below the bid fills THRU')
    def test_thru_mint_mirror_needs_strictly_above(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        at=pfav.score(EP,b,tape([(110,DN,0.30,50,0)]),(UP,DN),UP,{})
        self.assertEqual(at['PFAV_THRU'][3],0,'other token AT 1-bid must not fill THRU')
        ab=pfav.score(EP,b,tape([(110,DN,0.31,50,0)]),(UP,DN),UP,{})
        self.assertEqual(ab['PFAV_THRU'][3],1,'other token strictly above 1-bid fills THRU')
    def test_thru_is_a_subset_of_touch(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        for px in (0.68,0.69,0.70):
            r=pfav.score(EP,b,tape([(100,UP,px,50,0)]),(UP,DN),UP,{})
            if r['PFAV_THRU'][3]: self.assertEqual(r['PFAV'][3],1,f'THRU filled at {px} but TOUCH did not')
    def test_plus_1c_column_costs_more_on_a_win_and_is_flat_on_a_loss(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        w=pfav.score(EP,b,tape([(100,UP,0.69,50,0)]),(UP,DN),UP,{})['PFAV_THRU']
        self.assertAlmostEqual(w[5],10/0.70-10,places=9)
        self.assertAlmostEqual(w[6],10/0.71-10,places=9)
        self.assertLess(w[6],w[5],'+1c must reduce a winning trade')
        l=pfav.score(EP,b,tape([(100,UP,0.69,50,0)]),(UP,DN),DN,{})['PFAV_THRU']
        self.assertAlmostEqual(l[5],-10.0,places=9)
        self.assertAlmostEqual(l[6],-10.0,places=9,msg='a loss is the full stake either way')

    def test_sell_prints_do_not_fill_a_resting_buy(self):
        b=book({s:(0.70,0.29) for s in range(60,181)})
        sell=pfav.score(EP,b,tape([(100,UP,0.69,50,0,'SELL')]),(UP,DN),UP,{})
        self.assertEqual(sell['PFAV'][3],0,'a maker SELL print is not evidence our BUY filled')
        buy=pfav.score(EP,b,tape([(100,UP,0.69,50,0,'BUY')]),(UP,DN),UP,{})
        self.assertEqual(buy['PFAV'][3],1)

if __name__=='__main__': unittest.main(verbosity=2)
