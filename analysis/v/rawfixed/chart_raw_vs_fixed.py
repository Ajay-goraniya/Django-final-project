import csv, datetime as dt
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, matplotlib.dates as md
R=list(csv.DictReader(open('analysis/zurich/raw_vs_fixed_candles.csv')))
R.sort(key=lambda r:int(r['epoch']))
t=[dt.datetime.utcfromtimestamp(int(r['epoch'])) for r in R]
f=lambda k:[float(r[k] or 0) for r in R]
def cum(a):
    s=0;o=[]
    for x in a: s+=x;o.append(s)
    return o
RAW,FIX='#eb6834','#2a78d6'; INK,INK2,GRID,SURF='#0b0b0b','#52514e','#e6e5e0','#fcfcfb'
plt.rcParams.update({'font.size':11,'axes.edgecolor':GRID,'axes.labelcolor':INK2,'xtick.color':INK2,'ytick.color':INK2,
                     'axes.facecolor':SURF,'figure.facecolor':SURF,'axes.grid':True,'grid.color':GRID,'grid.linewidth':.6})
fig,ax=plt.subplots(3,1,figsize=(8,13),gridspec_kw=dict(height_ratios=[1,1,.8]))
fig.suptitle('RAW vs FIXED — TEST on Zurich candles, $10 stake\n(simulation, not your London account)',color=INK,fontsize=13,x=.02,ha='left')
def line(a,y,c,lab):
    a.plot(t,y,color=c,lw=2); a.annotate(f'{lab}  {y[-1]:+.0f}',(t[-1],y[-1]),xytext=(6,0),textcoords='offset points',color=INK,va='center',fontsize=10)
a=ax[0]; line(a,cum(f('paper_pnl_raw')),RAW,'RAW'); line(a,cum(f('paper_pnl_fixed')),FIX,'FIXED')
a.set_title('1. Paper: every order fills (what Zurich shows)',loc='left',color=INK); a.set_ylabel('cumulative $')
a=ax[1]
a.fill_between(t,f('exec_p05_cum_raw'),f('exec_p95_cum_raw'),color=RAW,alpha=.12,lw=0)
a.fill_between(t,f('exec_p05_cum_fixed'),f('exec_p95_cum_fixed'),color=FIX,alpha=.12,lw=0)
line(a,cum(f('exec_exp_pnl_raw')),RAW,'RAW'); line(a,cum(f('exec_exp_pnl_fixed')),FIX,'FIXED')
a.set_title("2. Same candles with London's real fills (misses, slippage, fees)\n   line = average of 1000 runs, band = 5th–95th %",loc='left',color=INK); a.set_ylabel('cumulative $')
for a in ax[:2]:
    a.axhline(0,color=INK2,lw=.8); a.xaxis.set_major_formatter(md.DateFormatter('%m-%d')); a.margins(x=.12)
    a.legend(['RAW','FIXED'] if a is ax[0] else ['RAW 5–95%','FIXED 5–95%','RAW','FIXED'],frameon=False,loc='upper left' if a is ax[0] else 'lower left',fontsize=9,ncol=1 if a is ax[0] else 2)
# 3: where raw's result comes from (paper)
both=[r for r in R if r['raw_fired']=='1' and r['fixed_fired']=='1']
ro=[r for r in R if r['raw_fired']=='1' and r['fixed_fired']!='1']
fo=[r for r in R if r['fixed_fired']=='1' and r['raw_fired']!='1']
s=lambda L,k:sum(float(r[k] or 0) for r in L)
cats=[f'both fire\n({len(both)})',f'RAW only\n({len(ro)})',f'FIXED only\n({len(fo)})']
rv=[s(both,'paper_pnl_raw'),s(ro,'paper_pnl_raw'),0]; fv=[s(both,'paper_pnl_fixed'),0,s(fo,'paper_pnl_fixed')]
a=ax[2]; x=range(3); w=.36
b1=a.bar([i-w/2-.01 for i in x],rv,w,color=RAW,label='RAW'); b2=a.bar([i+w/2+.01 for i in x],fv,w,color=FIX,label='FIXED')
for bars,vals in ((b1,rv),(b2,fv)):
    for b,v in zip(bars,vals):
        if v: a.annotate(f'{v:+.0f}',(b.get_x()+b.get_width()/2,v),xytext=(0,4 if v>0 else -12),textcoords='offset points',ha='center',color=INK,fontsize=9)
a.set_xticks(list(x)); a.set_xticklabels(cats); a.axhline(0,color=INK2,lw=.8); a.set_ylabel('paper $')
a.set_title("3. Where RAW's paper result comes from: its extra trades lose",loc='left',color=INK); a.legend(frameon=False,fontsize=9)
fig.tight_layout(rect=(0,0,1,.95)); fig.savefig('analysis/v/rawfixed/raw_vs_fixed.png',dpi=130)
print(len(R),len(both),len(ro),len(fo),rv,fv)
