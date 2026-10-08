import os
import json, collections, statistics as st, chess, sys
EVALS = sys.argv[1]; sys.argv = ['x', EVALS, '/dev/null']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stats.py'), encoding='utf-8').read().split('out = collections.OrderedDict()')[0])
def cls(l): return "Patzer" if l>=300 else "Fehler" if l>=100 else None
o={}
# erster Patzer in Niederlagen
fp=[]; fpc=collections.Counter(); fpv=collections.Counter(); fpp=collections.Counter()
for g in games:
    if g["res"]!="N": continue
    f=next((m for m in g["moves"] if m["mine"] and m["loss"]>=300),None)
    if not f: continue
    fp.append(f["no"]); c,v=classify(g,f); fpc[c]+=1; fpv[v]+=1
    fpp[NAME.get(g["boards"][f["i"]].piece_at(chess.Move.from_uci(f["move"]).from_square).piece_type,"König")]+=1
o["Niederlagen mit Patzer>=3"]=len(fp)
o["Erster Patzer: Zug-Median, Quartile"]=(st.median(fp), st.quantiles(fp,n=4))
h=collections.Counter("1-10" if n<=10 else "11-15" if n<=15 else "16-20" if n<=20 else "21-30" if n<=30 else ">30" for n in fp); o["Erster Patzer Zug"]=dict(sorted(h.items()))
o["Erster Patzer Ursache"]=dict(fpc.most_common()); o["Erster Patzer verlorene Figur"]=dict(fpv.most_common()); o["Erster Patzer gezogene Figur"]=dict(fpp.most_common())
# erster Fehler >=1: gezogene Figur & Zugart in Eröffnung
fe=collections.Counter()
for g in games:
    if g["res"]!="N": continue
    f=next((m for m in g["moves"] if m["mine"] and m["loss"]>=100),None)
    if not f: continue
    b=g["boards"][f["i"]]; mv=chess.Move.from_uci(f["move"]); p=b.piece_at(mv.from_square)
    k=NAME.get(p.piece_type,"König")
    if p.piece_type==chess.PAWN and chess.square_file(mv.from_square) in (0,1,6,7): k="Randbauer (a,b,g,h)"
    if p.piece_type==chess.PAWN and chess.square_file(mv.from_square)==5: k="f-Bauer"
    if b.is_capture(mv): k+=" (schlägt)"
    fe[k]+=1
o["Erster Fehler>=1: welche Figur gezogen"]=dict(fe.most_common())
# Verwertung: verlorene/remis Partien mit >=+5
lost_win=[]; 
for g in games:
    if g["res"] in "NR":
        ev=g["evs"][:-1]; 
        if max(ev or [0])>=500:
            k=max(range(len(ev)),key=lambda i:ev[i])
            lost_win.append((g["res"], g["boards"][k].fullmove_number, len(g["uci"])//2, g["h"]["Termination"].split(" - ")[-1]))
o["Gewinnstellung (>=+5) nicht gewonnen"]=collections.Counter(r for r,*_ in lost_win)
o["…davon Ende durch"]=dict(collections.Counter((r,t if "gewinnt" not in t else t.split("gewinnt")[1]) for r,_,_,t in lost_win).most_common())
# Material-Zustand bei Gewinnstellung nicht gewonnen: wie viel Material hatte ich?
# Zeitniederlagen/-siege
o["Remis-Arten"]=dict(collections.Counter(g["h"]["Termination"] for g in games if g["res"]=="R"))
# Dauer bis Matt nach Erreichen von >=+5 (Siege durch Matt)
d=[]
for g in games:
    if g["res"]=="S" and "Schachmatt" in g["h"]["Termination"]:
        k=next((i for i,e in enumerate(g["evs"]) if e>=500),None)
        if k is not None: d.append((len(g["evs"])-1-k)//2)
o["Siege durch Matt: Züge von +5 bis Matt (Median, Q3)"]=(st.median(d), st.quantiles(d,n=4)[2])
def ts(g):
    t=g["h"].get("EndTime","0:0:0").split()[0].split(":"); return g["h"]["Date"]+"%02d%02d%02d"%tuple(int(x) for x in t)
seqg=sorted(games,key=ts)
after=collections.defaultdict(collections.Counter)
for a,b in zip(seqg,seqg[1:]):
    if a["h"]["Date"]==b["h"]["Date"]: after[a["res"]][b["res"]]+=1
o["Ergebnis der nächsten Partie (gleicher Tag) nach S/N/R"]={k:dict(v) for k,v in after.items()}
# nach 2 Niederlagen in Folge
s2=collections.Counter()
for a,b,c in zip(seqg,seqg[1:],seqg[2:]):
    if a["res"]=="N" and b["res"]=="N" and a["h"]["Date"]==c["h"]["Date"]: s2[c["res"]]+=1
o["nach 2 Niederlagen in Folge"]=dict(s2)
# Nummer der Partie am Tag
byday=collections.defaultdict(list)
for g in seqg: byday[g["h"]["Date"]].append(g)
pn=collections.defaultdict(collections.Counter)
for day,gs in byday.items():
    for k,g in enumerate(gs):
        pn["1-5" if k<5 else "6-10" if k<10 else ">10"][g["res"]]+=1
o["Ergebnis nach Partie-Nr. am Tag"]={k:dict(v) for k,v in pn.items()}
# ACPL nach Partie-Nr.
for day in ("2026.09.12","2026.09.13"):
    o["Serie "+day]="".join(g["res"] for g in byday[day])
# Ø Fehler>=1 je Partie bei Weiß d4 vs e4 und erster Fehler-Zug
fe2=collections.defaultdict(list)
for g in games:
    if g["me"]!=chess.WHITE: continue
    f=next((m for m in g["moves"] if m["mine"] and m["loss"]>=300),None)
    fe2[g["uci"][0]].append(f["no"] if f else None)
o["Weiß: erster Patzer-Zug je 1. Zug (Median, Anteil mit Patzer bis Zug 12)"]={k:(st.median([x for x in v if x] or [0]), round(sum(1 for x in v if x and x<=12)/len(v),2), len(v)) for k,v in fe2.items() if len(v)>=10}
for k,v in o.items(): print(k,":",v)
