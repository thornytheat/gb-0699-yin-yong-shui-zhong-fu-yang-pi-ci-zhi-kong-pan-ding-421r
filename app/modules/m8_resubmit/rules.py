from app.report import report, quarantine


class DSU:
    """并查集：把同一物理样品的多个受理号并为一组。"""

    def __init__(self):
        self.parent = {}

    def add(self, x):
        if x not in self.parent:
            self.parent[x] = x

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != x:
            nxt = self.parent[x]
            self.parent[x] = root
            x = nxt
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
        return ra


def _physical_key(row):
    return (row["batch"], row["analyte"], row["pair"], row["kind"])


def merge(rows, ctx):
    """按 (batch, analyte) 分域建立受理号并查集，返回物理样品归并结果与无效补送边。"""
    domains = {}
    for r in rows:
        domains.setdefault((r["batch"], r["analyte"]), []).append(r)

    links, bad_edges, effective = [], [], []
    for domain, items in sorted(domains.items()):
        dsu = DSU()
        for r in items:
            dsu.add(r["id"])
        known = {r["id"] for r in items}
        first_seen = {}
        for r in sorted(items, key=lambda x: x["line"]):
            first_seen.setdefault(r["id"], r)
        seen_edges = set()
        # 先校验全部补送边：任何一条非法都不并入，保留原受理号独立状态（归并失败可恢复）
        valid_edges = []
        for r in sorted(items, key=lambda x: x["line"]):
            target = (r.get("resubmit") or "").strip()
            if not target:
                continue
            edge = (r["id"], target)
            if r["id"] == target:
                bad_edges.append((r, "RESUBMIT_SELF"))
                continue
            if edge in seen_edges:
                bad_edges.append((r, "RESUBMIT_DUPLICATE"))
                continue
            seen_edges.add(edge)
            if target not in known:
                bad_edges.append((r, "RESUBMIT_TARGET_MISSING"))
                continue
            original = first_seen[target]
            if (r["pair"], r["kind"]) != (original["pair"], original["kind"]):
                bad_edges.append((r, "RESUBMIT_IDENTITY_DRIFT"))
                continue
            valid_edges.append((r, target))
        # 环路检测：逐条并边前记录两端根，若已同根则成环
        for row, old_id in valid_edges:
            new_id = row["id"]
            if dsu.find(new_id) == dsu.find(old_id):
                bad_edges.append((row, "RESUBMIT_CYCLE"))
                continue
            dsu.union(new_id, old_id)
            links.append({"batch": domain[0], "analyte": domain[1], "new_id": new_id,
                          "original_id": old_id, "line": row["line"]})

        groups = {}
        for r in items:
            groups.setdefault(dsu.find(r["id"]), []).append(r)
        for root, members in sorted(groups.items()):
            # 当前值取最高版本；同版本取最后确认（行号最大），迟到的旧版补送不会退回当前结论
            canonical = max(members, key=lambda x: (x["rev"], x["line"]))
            aliases = sorted({m["id"] for m in members})
            pkey = _physical_key(canonical)
            for m in members:
                m["physical_key"] = list(pkey)
                m["physical_sample"] = canonical["id"]
                m["accept_aliases"] = aliases
                m["original_id"] = canonical["id"] if m["id"] != canonical["id"] else ""
                m["is_current"] = m["id"] == canonical["id"]
            cur = dict(canonical)
            cur["accept_aliases"] = aliases
            cur["history_versions"] = sorted({m["rev"] for m in members})
            cur["history_lines"] = sorted(m["line"] for m in members)
            effective.append(cur)
    return effective, links, bad_edges


def apply(ctx):
    rows = ctx["normalized"]
    effective, links, bad_edges = merge(rows, ctx)
    for row, reason in bad_edges:
        quarantine(ctx, row, reason)
    # 归并失败的补送边不执行合并：相关受理号按最后确认值独立参与质控（可恢复、不丢记录）
    ctx["effective"] = effective
    ctx["resubmit_links"] = links
    ctx["physical_samples"] = [
        {"physical_sample": r["id"], "aliases": r["accept_aliases"],
         "batch": r["batch"], "analyte": r["analyte"], "current_id": r["id"],
         "current_version": r["rev"], "line": r["line"]}
        for r in ctx["effective"] if len(r["accept_aliases"]) > 1
    ]
    return report(ctx["physical_samples"],
                  物理样品=len({tuple(r["physical_key"]) for r in ctx["effective"]}),
                  补送归并=len(links), 归并失败=len(bad_edges),
                  有效受理号=len(ctx["effective"]), 历史版本=len(rows)-len(ctx["effective"]))
