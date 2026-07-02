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

评分故意保持简单：

- 主题直接命中：明显加分；设置时间范围时，年份也会进入搜索词，比如自动搜索 `2025`、`2026`
- 标题或摘要里出现“案例、复盘、拆解、解码、趋势、观察、洞察、报告、策略、增长、商业化”等内容价值词：加分
- 如果文章来自“案例、复盘、研究、趋势、分析”等搜索词，也会少量加分
- 摘要比较完整时，会少量加分，避免好文章因为标题太短被漏掉
- 如果主题被识别为营销类，标题里出现“品牌、赞助、联名、投放、传播、消费者、场景、心智、破圈”等营销词：加分
- 摘要里出现内容价值词：少量加分
- 公众号名称像营销、品牌、商业、财经、数据、洞察、研究、产业、行业、科技类账号：加分
- 出现招聘、课程、资料包、下载等噪音词：重扣分
- 出现周报、榜单、官宣、通知、合规、研析、直播等低价值格式词：扣分

分数只分三档：`strong`、`maybe`、`weak`。现在会优先保留真正像案例、复盘、趋势、观察、策略分析的文章，而不是只因为标题里带关键词就排到前面。

## 后台浏览器复核

脚本会尝试用本机 Chrome 或 Edge 的无窗口模式复核搜狗跳转链接，中间加入 2 到 6 秒随机间隔。这个过程不会弹出浏览器窗口。
