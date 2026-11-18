from app.reader import read_rows
from app.report import report,quarantine
FIELDS="id batch analyte kind pair value spike unit version".split()
OPTIONAL_FIELDS=["resubmit"]
def apply(ctx):
    rows,bad,blank=read_rows(ctx["text"],FIELDS+OPTIONAL_FIELDS,optional=set(OPTIONAL_FIELDS));ctx["quarantine"].extend(bad);ctx["blank_rows"]=blank;ctx["input_count"]=len(rows)+len(bad)+blank
    out=[];seen=set()
    for r in rows:
        r.setdefault("resubmit","")
        key=(r["batch"],r["analyte"],r["id"],r["version"])
        if not r["id"]:quarantine(ctx,r,"ID_REQUIRED");continue
        if key in seen:quarantine(ctx,r,"VERSION_CONFLICT");continue
        seen.add(key);out.append(r)
    ctx["raw"]=out;return report(out,样品=len(out),隔离=len(ctx["quarantine"]))
