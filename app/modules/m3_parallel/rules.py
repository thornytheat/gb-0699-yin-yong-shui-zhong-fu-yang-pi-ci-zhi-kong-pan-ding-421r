from decimal import Decimal
from app.report import report

def pair_check(a,b,mdl=Decimal("0.001"),censored=False):
    if censored:return {"status":"CENSORED_REVIEW","metric":None,"limit":None,"method":"限定值"}
    mean=(a+b)/2;diff=abs(a-b)
    if mean<5*mdl:return {"status":"PASS" if diff<=mdl else "PAIR_FAIL","metric":diff,"limit":mdl,"method":"绝对差mg/L"}
    relative=diff/mean
    return {"status":"PASS" if relative<=Decimal("0.20") else "PAIR_FAIL","metric":relative,"limit":Decimal("0.20"),"method":"相对偏差"}

def _key(r):
    return tuple(r["physical_key"]) if "physical_key" in r else (r["batch"],r["analyte"],r["pair"],r["kind"])

def apply(ctx):
    groups={}
    for r in ctx["effective"]:
        if r["kind"] in {"sample","duplicate"}:groups.setdefault(_key(r)[:3],[]).append(r)
    out=[]
    for key,rows in sorted(groups.items()):
        left=[r for r in rows if r["kind"]=="sample"];right=[r for r in rows if r["kind"]=="duplicate"]
        if len(left)!=1 or len(right)!=1:out.append({"batch":key[0],"analyte":key[1],"pair":key[2],"status":"PAIR_MISSING","metric":None,"limit":None,"method":"配对"});continue
        ls,ds=left[0],right[0]
        check=pair_check(ls["value_mg"],ds["value_mg"],censored=ls["censored"] or ds["censored"])
        out.append(dict(batch=key[0],analyte=key[1],pair=key[2],
                        physical_sample=ls.get("physical_sample",ls["id"]),
                        current_id=ls["id"],accept_aliases=ls.get("accept_aliases",[ls["id"]]),
                        duplicate_id=ds["id"],
                        left=ls["value_mg"],right=ds["value_mg"],line=ls["line"],**check))
    ctx["parallel"]=out;return report(out,配对=len(out),失败=sum(r["status"]!="PASS" for r in out))
