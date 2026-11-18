# 饮用水重复样与批次质控判定

水质监测数据复核员使用本工具归并采样平行样、加标样、空白样，对检测批给出放行结论。

## 核心计算

双样相对偏差分母零时单独判定；低浓度用绝对差阈值，高浓度用相对偏差；加标回收扣除本底。

## 启动

```bash
docker compose up --build -d
docker compose exec -T app pytest -q
docker compose config --quiet
```

浏览器访问 http://localhost:18213 。默认载入仓内样例。工具条可选择CSV文件运行；样例文件位于 `sample_data/instrument.csv`。重复执行同一内容复用同一批次。

## 模块

- M1 样品接收：`/module/1`，独立计算 `POST /api/1`。
- M2 检测项契约：`/module/2`，独立计算 `POST /api/2`。
- M8 补送归并：`/module/3`，独立计算 `POST /api/8`。
- M3 平行样核对：`/module/4`，独立计算 `POST /api/3`。
- M4 加标回收：`/module/5`，独立计算 `POST /api/4`。
- M5 空白污染：`/module/6`，独立计算 `POST /api/5`。
- M6 批次放行：`/module/7`，独立计算 `POST /api/6`。
- M7 复测追踪：`/module/8`，独立计算 `POST /api/7`。

## 转瓶补送（M8）

采样瓶转瓶补送会产生新受理号。CSV 可选列 `resubmit` 填写该补送记录所替代的原受理号（无补送可整列省略，旧文件直接兼容）。系统按检测批+检测项分域，用并查集把同一物理瓶的多个受理号并为一个物理样品：

- 批次放行与各质控只采信每个物理样品的当前值（最高 `version`，同版本取最后确认行）；原受理号、原始行号、平行样证据全部保留可查，补送不会被重复算成独立质控。
- 归并失败（目标受理号不存在 `RESUBMIT_TARGET_MISSING`、自引用 `RESUBMIT_SELF`、重复补送边 `RESUBMIT_DUPLICATE`、闭环 `RESUBMIT_CYCLE`、物理身份漂移 `RESUBMIT_IDENTITY_DRIFT`）逐边隔离且不执行该边合并，从最后确认的样品恢复为独立记录，不丢数据。
- 同批补送重试按输入摘要幂等，不新增批次记录；迟到的低版本补送不会把当前结论退回。
- 页面与证据导出同时呈现新受理号、原受理号（`accept_aliases`）与当前值。带补送的样例见 `sample_data/instrument-resubmit.csv`。

## 输入与输出

CSV可用UTF-8或GB18030；上传保留字符串编号和物理行号。POST `/api/run` 接收 `text` 字段。`GET /api/runs` 查询历史，`POST /api/review` 接收 id、revision、decision。导出按钮下载唯一证据CSV，含运行摘要与隔离记录。

SQLite命名卷保存运行记录。重建演示数据可更换卷名后重启。无需外部网络数据。规则定义见 `docs/DATA-DICTIONARY.md`；边界和测试对应关系见 `docs/DEPTH.md`。

## 范围

只处理仓内CSV定义，不连接生产系统。单次输入最多2MB。原始输入流式解析，业务计算阶段需容纳该文件的采信行。并非无限容量任务。
