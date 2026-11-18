# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本与输入摘要只产生一条批次。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。`/api/8` 为补送归并，额外返回 links（新受理号→原受理号）。注意流水线顺序中补送归并位于第3位（页面 `/module/3`），路由号沿用模块编号 M8。

`POST /api/review`：id、整数revision、decision取通过或退回。旧版本409；阻断项不能通过。

`GET /api/export/{id}`：唯一证据CSV，含 `resubmit_link`（两类受理号关联）与 `physical_sample`（物理样品当前值与全部别名）区块。`GET /health`：存活检查。

转瓶补送：CSV 可选 `resubmit` 列指向原受理号。归并失败原因码：`RESUBMIT_TARGET_MISSING`、`RESUBMIT_SELF`、`RESUBMIT_DUPLICATE`、`RESUBMIT_CYCLE`、`RESUBMIT_IDENTITY_DRIFT`（补送记录的配对号或样品类别与原瓶不一致），失败边隔离并恢复为独立样品。

错误：结构/数值422，版本冲突409，不存在404，文件过大413。逐行异常进入quarantine。
