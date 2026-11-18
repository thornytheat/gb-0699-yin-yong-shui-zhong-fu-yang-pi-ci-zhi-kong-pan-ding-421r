def execute(text):
    from app.pipeline import run
    result=run(text)
    return {"module":8, "report":result["reports"][2], "quarantine":result["quarantine"], "balance":result["balance"],
            "links":result["resubmit_links"]}
