from app.report import report

def next_version(current,proposed):
    if proposed<=current:raise ValueError("复测版本须递增")
    return proposed

def apply(ctx):
    failed={(r["batch"],r["analyte"]) for r in ctx["released"] if r["status"]!="PASS"}
    out=[]
    for r in ctx["effective"]:
        if (r["batch"],r["analyte"]) in failed:
            out.append({"id":r["id"],"physical_sample":r.get("physical_sample",r["id"]),
                        "original_id":r.get("original_id",""),"accept_aliases":r.get("accept_aliases",[r["id"]]),
                        "batch":r["batch"],"analyte":r["analyte"],"kind":r["kind"],
                        "current_version":r["rev"],"required_version":next_version(r["rev"],r["rev"]+1),
                        "status":"RETEST","line":r["line"]})
    ctx["final"]=out;return report(out,复测任务=len(out),有效样品=len(ctx["effective"]))
