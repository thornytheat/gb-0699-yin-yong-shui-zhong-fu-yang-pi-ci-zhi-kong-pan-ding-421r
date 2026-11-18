import csv,io,json

def evidence_csv(run):
    out=io.StringIO();writer=csv.writer(out)
    result=run["result"]
    writer.writerow(["run_id","sha256","rule_version","kind","line","reason","evidence"])
    writer.writerow([run["id"],run["digest"],run["rule_version"],"manifest","","",json.dumps({"balance":result["balance"],"decision":run["decision"],"revision":run["revision"]},ensure_ascii=False)])
    for link in result.get("resubmit_links",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"resubmit_link",link.get("line",""),"",
                         json.dumps({"new_id":link["new_id"],"original_id":link["original_id"],
                                     "batch":link["batch"],"analyte":link["analyte"]},ensure_ascii=False)])
    for row in result.get("physical_samples",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"physical_sample",row.get("line",""),"",json.dumps(row,ensure_ascii=False)])
    for row in result.get("final",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"result",row.get("line",""),row.get("status",""),json.dumps(row,ensure_ascii=False)])
    for row in result.get("quarantine",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"quarantine",row.get("line",""),row["reason"],json.dumps(row,ensure_ascii=False)])
    return "﻿"+out.getvalue()
