"""Render the publication's existing statistical layouts as editable SVG."""
from pathlib import Path
from collections import defaultdict
from html import escape
import csv,json,math,subprocess
import numpy as np
import argparse
HERE=Path(__file__).resolve().parent
ROOT=None
DATA=None
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--artifact-root',type=Path,required=True);args=p.parse_args()
ROOT=args.artifact_root/'04_Reproducibility/02_Published_Evaluation'
DATA=args.artifact_root/'02_Figures/02_Plot_Data'
def csvwrite(path,rows):
 with path.open('w',newline='',encoding='utf-8-sig')as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
OUT=Path(args.out).resolve();OUT.mkdir(parents=True,exist_ok=True)
BLUE='#2D637F';RUST='#AD5738';GRID='#E8ECEF'
class SVG:
 def __init__(self,w,h):
  self.w=w*72;self.h=h*72;self.s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}in" height="{h}in" viewBox="0 0 {self.w} {self.h}"><rect width="100%" height="100%" fill="white"/><g font-family="Helvetica, Arial, sans-serif" fill="#222">']
 def text(self,x,y,s,size=7,anchor='start',fill='#222',weight='normal',rotate=None):
  tr=f' transform="rotate({rotate} {x} {y})"'if rotate else''
  self.s.append(f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}"{tr}>{escape(str(s))}</text>')
 def line(self,x,y,X,Y,color=GRID,width=.55):self.s.append(f'<line x1="{x:.3f}" y1="{y:.3f}" x2="{X:.3f}" y2="{Y:.3f}" stroke="{color}" stroke-width="{width}"/>')
 def dot(self,x,y,r=1.4,color=BLUE,opacity=1,open=False,diamond=False,shape=None):
  if shape=='triangle':self.s.append(f'<path d="M{x},{y-r}L{x+r},{y+r}L{x-r},{y+r}Z" fill="{color}" opacity="{opacity}"/>')
  elif shape=='square':self.rect(x-r,y-r,r*2,r*2,color)
  elif diamond or shape=='diamond':self.s.append(f'<path d="M{x},{y-r}L{x+r},{y}L{x},{y+r}L{x-r},{y}Z" fill="{color}" opacity="{opacity}"/>')
  else:self.s.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r}" fill="{"white"if open else color}" stroke="{color}" stroke-width=".45" opacity="{opacity}"/>')
 def rect(self,x,y,w,h,fill,stroke='none',width=.5):self.s.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
 def save(self,name):
  p=OUT/(name+'.svg');p.write_text(''.join(self.s)+'</g></svg>');return p
def xaxis(g,x0,x1,y,vals,domain,label):
 for v in vals:
  x=x0+(v-domain[0])/(domain[1]-domain[0])*(x1-x0);g.text(x,y+10,str(v),6.5,'middle')
 g.text((x0+x1)/2,y+24,label,7.5,'middle')
models=sorted(rows(DATA/'models.csv'),key=lambda r:int(r['order']))
names={r['model']:r['name']for r in models};order=[r['model']for r in models]
scores=[r for r in rows(ROOT/'projection/scores.csv')if r['condition']=='i0']
rng=np.random.default_rng(20261110)

g=SVG(3.39,3.53);top=26;bottom=224;rowh=(bottom-top)/11
for col,metric in enumerate(['field_f1','record_f1']):
 x0=85+col*80;x1=x0+70
 for v in [0,50,100]:x=x0+v/100*(x1-x0);g.line(x,17,x,bottom+8)
 g.text((x0+x1)/2,12,'Field F1'if col==0 else'Record F1',8,'middle',weight='bold')
 for i,m in enumerate(order):
  y=top+i*rowh
  if not col:g.text(80,y+2.5,names[m],6.5,'end')
  rr=[r for r in scores if r['model']==m and r[metric]!=''];v=np.array([100*float(r[metric])for r in rr]);q1,med,q3=np.quantile(v,[.25,.5,.75]);iqr=q3-q1
  lo=min(v[v>=q1-1.5*iqr]);hi=max(v[v<=q3+1.5*iqr]);xx=lambda v:x0+v*.7
  g.line(xx(lo),y,xx(hi),y,BLUE,.65);g.rect(xx(q1),y-4.2,(q3-q1)*.7,8.4,'#E5EEF6',BLUE,.6);g.line(xx(med),y-4.2,xx(med),y+4.2,BLUE,.85)
  for r,vr in zip(rr,v):
   yy=y+float(rng.uniform(-1.8,1.8));x=xx(vr)
   if r['zero_output']=='True':g.line(x-1.5,yy-1.5,x+1.5,yy+1.5,RUST,.7);g.line(x-1.5,yy+1.5,x+1.5,yy-1.5,RUST,.7)
   else:g.dot(x,yy,.72,BLUE,.28)
 xaxis(g,x0,x1,bottom+7,[0,50,100],(0,100),'')
g.text(163,250,'Study F1 (%)',8,'middle');g.save('Figure3')

ef={r['model']:r for r in rows(ROOT/'efe-actual/model_summary.csv')if r['domain']=='overall'and r['metric']=='misattribution_rate'}
g=SVG(3.39,3.47);x0,x1=96,236
for v in [0,3,6,9,12]:x=x0+v/12*(x1-x0);g.line(x,8,x,220)
for i,m in enumerate(order):
 y=17+i*18;g.text(91,y+2.5,names[m],6.5,'end');r=ef[m];point,lo,hi=[100*float(r[k])for k in ['estimate','low','high']];xx=lambda v:x0+v/12*(x1-x0);c=RUST if m=='qwen'else BLUE
 g.line(xx(lo),y,xx(hi),y,c,.65);g.dot(xx(point),y,1.8,c,diamond=m=='qwen')
xaxis(g,x0,x1,221,[0,3,6,9,12],(0,12),'Misattributed fields (%)');g.save('Figure4')

diag=rows(ROOT/'diagnostic-summary.csv');g=SVG(3.39,2.32);x0,x1=89,236
for v in [0,25,50,75,100]:x=x0+v/105*(x1-x0);g.line(x,26,x,131)
for i,(cat,label)in enumerate([('omission','Evidence omission'),('binding','Binding error'),('grounding','Grounding error'),('constraint','Constraint violation')]):
 y=41+i*27;g.text(84,y+2,label,6.7,'end');points=[]
 for d,c,dy in [('clinical',BLUE,-1),('basic',RUST,1)]:
  r=next(r for r in diag if r['domain']==d and r['model']=='ALL'and r['category']==cat);v=float(r['percentage']);x=x0+v/105*(x1-x0);points.append(x);g.dot(x,y+dy,2,c,diamond=d=='basic');g.text(x,y+(-6 if d=='clinical' else 11),f'{v:.1f}',6,'middle',fill=c)
 g.line(min(points)+2,y,max(points)-2,y,'#D8DEE2',.45)
g.dot(115,11,1.7,BLUE);g.text(120,13,'Clinical',6.5);g.dot(166,11,1.7,RUST,diamond=True);g.text(171,13,'Basic research',6.5)
xaxis(g,x0,x1,137,[0,25,50,75,100],(0,105),'Answers with the error (%)');g.save('Figure5')

width=[r for r in rows(ROOT/'width-results.csv')if r['sensitivity']=='False' and 2<=int(r['width'])<=9];g=SVG(3.39,4.9);x0,x1=36,236;y0,y1=31,151
g.text(8,13,'a  Record width and recovery',8,weight='bold')
for v in [0,25,50,75,100]:y=y1-v/100*(y1-y0);g.line(x0,y,x1,y);g.text(x0-5,y+2,str(v),6,'end')
kinds=sorted({(r['domain'],r['table'])for r in width})
occupied_labels=[]
width_points=[]
for j,(d,t)in enumerate(kinds):
 for r in [r for r in width if(r['domain'],r['table'])==(d,t)]:
  x=x0+(int(r['width'])-2)/7*(x1-x0)+(j-3)*1.8;y=y1-float(r['estimate_study_equal'])*(y1-y0);c=BLUE if d=='clinical'else RUST
  if int(r['n_studies'])>=5:g.line(x,y1-float(r['low'])*(y1-y0),x,y1-float(r['high'])*(y1-y0),c,.4)
  shape={'condition':'triangle','population':'triangle','assay_run':'square','population_relation':'square','result':'diamond'}.get(t)
  g.dot(x,y,1.6,c,shape=shape)
  width_points.append((x,y,c,str(r['n_studies'])))
for x,y,c,label in width_points:
 tw=len(label)*2.5;candidates=[]
 for dy in [-4,-11,10,17,-18,24]:
  for dx in [2,-tw-2,8,-tw-8]:
   lx=x+dx;ly=y+dy;box=(lx,ly-5,lx+tw,ly+1)
   if box[0]<x0 or box[2]>239 or box[1]<y0 or box[3]>y1+1:continue
   if any(box[0]<b[2]+1 and box[2]>b[0]-1 and box[1]<b[3]+1 and box[3]>b[1]-1 for b in occupied_labels):continue
   if any(box[0]-2<px<box[2]+2 and box[1]-2<py<box[3]+2 for px,py,_,_ in width_points):continue
   candidates.append((abs(dy)+abs(dx)*.35,lx,ly,box))
 if not candidates:raise ValueError('No width label position')
 _,lx,ly,box=min(candidates);occupied_labels.append(box);g.text(lx,ly,label,4.7,fill=c)
xaxis(g,x0,x1,y1+3,list(range(2,10)),(2,9),'Scientific fields per record');g.text(8,93,'Record recall (%)',7,'middle',rotate=-90)
for j,(d,t)in enumerate(kinds):
 x=33+(j%2)*104;y=194+(j//2)*8;c=BLUE if d=='clinical'else RUST;shape={'condition':'triangle','population':'triangle','assay_run':'square','population_relation':'square','result':'diamond'}.get(t);g.dot(x,y-2,1.4,c,shape=shape);g.text(x+4,y,('Clinical 'if d=='clinical'else'Basic ')+t.replace('_',' '),5.3)
g.text(8,241,'b  Relation recovery',8,weight='bold');y0,y1=254,319
for v in [0,25,50,75,100]:y=y1-v/100*(y1-y0);g.line(x0,y,x1,y);g.text(x0-5,y+2,str(v),6,'end')
by=defaultdict(list)
for r in rows(ROOT/'efe-actual/study_counts.csv'):
 if int(r.get('relation_gold')or 0):by[r['domain'],r['case']].append((int(r['relation_gold']),int(r['relation_tp'])/int(r['relation_gold'])))
points=[]
for(d,c),vs in by.items():
 n=vs[0][0];rate=float(np.mean([v[1]for v in vs]));x=x0+(math.log10(n)-math.log10(2))/(math.log10(300)-math.log10(2))*(x1-x0);y=y1-rate*(y1-y0);g.dot(x,y,1.6,BLUE if d=='clinical'else RUST,.8,shape='triangle'if d=='basic'else None);points.append(dict(domain=d,case=c,relation_count=n,recall=rate))
for v in[2,5,10,20,50,100,250]:x=x0+(math.log10(v)-math.log10(2))/(math.log10(300)-math.log10(2))*(x1-x0);g.text(x,y1+10,v,6,'middle')
g.text((x0+x1)/2,348,'Reference links per study (log scale)',7,'middle');g.text(8,286,'Relation recall (%)',7,'middle',rotate=-90);g.save('Figure6');csvwrite(OUT/'relation_study_points.csv',points)

quality={r['model']:r for r in rows(ROOT/'quality-analysis/i0/absolute.csv')if r['domain']=='overall'};cost=rows(DATA/'quality_cost.csv');g=SVG(3.39,3.87);x0,x1=36,235;y0,y1=15,236;lo,hi=66,90
for v in [70,75,80,85,90]:y=y1-(v-lo)/(hi-lo)*(y1-y0);g.line(x0,y,x1,y);g.text(x0-5,y+2,v,6,'end')
rank=sorted(order,key=lambda m:-float(quality[m]['field_f1_mean']))
points={}
for m in order:
 r=next(r for r in cost if r['model']==m);v=float(r['cost']);rate=100*float(quality[m]['field_f1_mean']);r['f1_pct']=rate;x=x0+(math.log10(v)-math.log10(.02))/(math.log10(3)-math.log10(.02))*(x1-x0);y=y1-(rate-lo)/(hi-lo)*(y1-y0);points[m]=(x,y,int(r['cost_n'])<100)
placements=[]
for m in rank:
 x,y,_=points[m];tw=len(names[m])*3.02
 candidates=[]
 for dy in [-5,10,-14,19,-23,28,-32,37,-41,46]:
  for dx in [5,-5,14,-14]:
   lx=x+dx if dx>0 else x+dx-tw;ly=y+dy;box=(lx,ly-6.5,lx+tw,ly+1.5)
   if box[0]<x0 or box[2]>x1 or box[1]<5 or box[3]>y1-2:continue
   if any(box[0]<b[2]+2 and box[2]>b[0]-2 and box[1]<b[3]+2 and box[3]>b[1]-2 for _,_,_,_,b in placements):continue
   if any(box[0]-2<px<box[2]+2 and box[1]-2<py<box[3]+2 for px,py,_ in points.values()):continue
   candidates.append((abs(dy)+abs(dx)*.3,lx,ly,box))
 if not candidates:raise ValueError('No collision-free label position for '+m)
 _,lx,ly,box=min(candidates);placements.append((m,lx,ly,tw,box))
for m,lx,ly,tw,box in placements:
 x,y,_=points[m];tx=max(lx,min(x,lx+tw));ty=ly-3;g.line(x,y,tx,ty,'#AAB6BD',.4)
for m,lx,ly,tw,box in placements:g.rect(lx-1,ly-6.5,tw+2,8,'white');g.text(lx,ly,names[m],6.1)
for x,y,open_marker in points.values():g.dot(x,y,2,BLUE,open=open_marker)
for v in [.025,.1,.5,2.5]:x=x0+(math.log10(v)-math.log10(.02))/(math.log10(3)-math.log10(.02))*(x1-x0);g.text(x,251,str(v),6,'middle')
g.text((x0+x1)/2,269,'Cost per study (USD, log scale)',7,'middle');g.text(9,126,'Overall Field F1 (%)',7,'middle',rotate=-90);g.save('Figure7');csvwrite(OUT/'quality_cost.csv',cost)

case_order=sorted({r['case']for r in scores},key=lambda c:(0 if c.startswith('C')else 1,-np.mean([float(r['field_f1'])for r in scores if r['case']==c]),c));lookup={(r['case'],r['model']):r for r in scores};g=SVG(6.45,7.82);cw,ch=15.5,4.3;y0=23
for col,metric in enumerate(['field_f1','record_f1']):
 x0=38+col*210;g.text(x0+6*cw,13,'Field F1'if col==0 else'Record F1',8,'middle',weight='bold')
 for i,c in enumerate(case_order):
  if i%5==0 and col==0:g.text(x0-4,y0+i*ch+3,c,5.7,'end')
  for j,m in enumerate(order):
   s=lookup[c,m][metric]
   if s=='':color='#CCCCCC'
   else:
    v=float(s);low=np.array([245,247,248]);high=np.array([27,66,93]);rgb=np.rint(low*(1-v)+high*v).astype(int);color='#'+''.join(f'{x:02x}'for x in rgb)
   g.rect(x0+j*cw,y0+i*ch,cw-.15,ch-.12,color)
   if lookup[c,m]['zero_output']=='True' and s!='':
    cx=x0+j*cw+cw/2;cy=y0+i*ch+ch/2
    g.line(cx-1.5,cy-1.5,cx+1.5,cy+1.5,RUST,.65);g.line(cx-1.5,cy+1.5,cx+1.5,cy-1.5,RUST,.65)
 for j,m in enumerate(order):g.text(x0+j*cw+cw/2,462,names[m],5.5,'end',rotate=-60)
g.text(232,555,'F1 (%)   light 0  →  dark 100     gray: no source-evaluable complete target',6,'middle');g.save('FigureA1')
print('Statistical SVG layouts generated in',OUT)
