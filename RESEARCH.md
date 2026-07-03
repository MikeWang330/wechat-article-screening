# 公众号文章搜索工具

这个工具只负责“找到可能有用的公众号文章链接”，不负责 MinerU 解析。它会自动生成搜索词、做简单筛选，并用后台浏览器复核跳转链接。

## 推荐用法

默认是一站式流程：自动搜索、筛选候选、后台转换成真实公众号链接，并把最终链接写入 `urls.txt`：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "AI 硬件营销" -Count 20
```

如果要从主题直接跑到 MinerU 解析结果：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI 硬件营销" -Count 20
```

如果只想完成找链接这一步，不跑 MinerU：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI 硬件营销" -Count 20 -SkipMinerU
```

如果只想生成候选清单，不改 `urls.txt`：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "AI 硬件营销" -Count 20 -NoWriteUrls
```

如果你想补充更明确的方向：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "AI 硬件营销" -Count 20 -ExtraKeywords "品牌案例,新品发布,渠道增长"
```

如果主题不是营销相关，可以强制用通用研究模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_project.ps1 -Topic "AI 硬件产业链" -Count 20 -Focus general
```

如果你只想要某个时间范围内的文章：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "世界杯营销" -Count 20 -StartDate "2025-01-01" -EndDate "2026-07-02"
```

也可以只填开始日期或结束日期：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_research.ps1 -Topic "AI 硬件营销" -Count 20 -StartDate "2025-01-01"
```

## 输出位置

- `candidates/*.md`：适合直接看的候选清单
- `candidates/*.csv`：最终选中的 URL 清单
- `candidates/*-screened-pool.csv`：筛选后参与转换的候选池，默认是 `Count * 2`
- `urls.txt`：默认会被替换成最终选中的真实公众号链接；加 `-NoWriteUrls` 时不会改

## 筛选逻辑

默认按“饮料公司商业分析部门”预设筛选，完整标准见 `SCREENING_STANDARD.md`。

核心规则：

- 主题相关只是门槛，不等于自动入选。
- 优先选择案例复盘、行业分析、数据报告、深度访谈、策略拆解。
- 加分信号包括市场、行业、竞品、渠道、终端、价格带、份额、消费者、投放、增长、供应链。
- 有数据、调研、样本、同比、市场份额、财报、图表、访谈等证据会加分。
- 饮料/快消语境会加分，例如饮料、包装水、电解质水、功能饮料、便利店、商超、经销商、货架、SKU。
- 招聘、课程、资料包、下载、通知、直播预告、浅层榜单、纯体育比分或赛程会扣分或拒绝。

搜索也改成轮次制：每轮只用一个关键词收集少量候选，立刻判断是否新增合格候选；达到候选池目标或连续两轮没有新增合格候选时自动停止。这样可以减少风控，也避免为了凑数引入弱相关内容。

分数分三档：`strong`、`maybe`、`weak`。最终只写入经过验证的 `mp.weixin.qq.com` 链接；如果不够数量，宁可少给。

## 后台浏览器复核

脚本会尝试用本机 Chrome 或 Edge 的无窗口模式复核搜狗跳转链接，中间加入 2 到 6 秒随机间隔。这个过程不会弹出浏览器窗口。
