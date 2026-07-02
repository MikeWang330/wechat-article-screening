---
name: wechat-article-screening
description: Question-led workflow for finding, screening, and selecting WeChat public-account articles. Use when an AI agent must turn a vague research need into an automatic-mode command, search queries, candidate scoring, clarified inclusion/exclusion rules, and final mp.weixin.qq.com URLs for tools such as MinerU. Suitable for marketing, industry, policy, company, technology, product, sports, and other WeChat article research topics.
---

# WeChat Article Screening

Use this skill to help a user find useful WeChat public-account articles, especially when the topic is broad or ambiguous. Work like a research partner: clarify the user's actual job-to-be-done, save stable screening preferences to the project's local `research_memory.json` when available, then turn the user's need into the project's automatic mode whenever the project scripts are available.

The preferred handoff is `run_auto.ps1`, which searches, screens, resolves real WeChat article links, writes `urls.txt`, and then runs MinerU. Only produce a manual `urls.txt` workflow when the user already provides article URLs or explicitly asks not to use automatic mode.

For a portable prompt that can be pasted into Claude, ChatGPT, DeepSeek, or another AI assistant, use `references/universal-prompt.md`.

## Principle

Do not assume keyword matches equal relevance. A good article may have a weak title but a strong abstract, credible account, or useful article body. A bad article may have a perfect title but be a notice, listicle, old recap, repost, or low-value news item.

Prioritize fit to the user's intent over generic popularity. Relevance is graded, not binary: a useful background or adjacent case may be worth keeping when exact articles are sparse.

## Automatic Mode Handoff

When this skill is used inside this project, the normal final action is to prepare or run an automatic-mode command:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_auto.ps1 -Topic "<topic plus important constraints>" -Count <count>
```

Use these rules:

- Put the user's real intent into `-Topic`, including key brands, entities, article type, exclusions, and context when they are important.
- Use `-Count` from the user's requested final number. Default to 20 if unknown.
- Choose `-Mode slow` by default. Use `-Mode fast` when the user wants a quick preview, low runtime, or says not to spend too long. Use `-Mode slow` when the user asks to find as many as possible or get close to the requested count.
- Add `-StartDate` and `-EndDate` only when the user gave an explicit date range. If no date range is given, let `run_auto.ps1` use its default recent-year window.
- Add `-ExtraKeywords` only for important disambiguation terms, required entities, or exclusions that would be awkward to pack into the topic.
- Add `-OnlyUrls` only when the user wants to stop after generating `urls.txt` and not run MinerU.
- Use graded relevance. Prefer exact matches first, then articles that are useful for writing a report on the topic. If exact matches are sparse, include clearly useful core-related context instead of returning an unnecessarily tiny list.
- Keep runtime bounded. In `fast` mode, use a screening pool no larger than `count * 2`. In `slow` mode, allow broader search up to about `count * 3`, but do not keep launching manual extra rounds indefinitely just to force an exact count.
- Stay on the high-level project entry point. Do not bypass `run_auto.ps1` to call low-level scripts with larger query limits unless the user explicitly asks for a custom research run.
- If automatic mode returns fewer usable articles than requested, report the shortfall and use the best verified articles. Do not keep expanding date ranges, adding unrelated keywords, or manually stitching weak results just to reach the requested number.

After asking clarifying questions, either run the command or show the exact command the user should run. Keep the command simple; do not expose low-level research parameters unless the user asks.

## Ask First

On a user's first run, ask a slightly richer but still lightweight intake. The goal is to learn the user's research pattern, not to make them operate the tool. Prefer 3 to 5 short questions when preferences are unknown. On later runs, reuse known preferences and ask only when the new request conflicts with them or is genuinely ambiguous.

After the first successful clarification, save stable preferences to local project memory when the project directory is writable:

1. If `research_memory.json` does not exist and `research_memory.example.json` exists, copy the example to `research_memory.json`.
2. Update only stable preferences in `research_memory.json`, such as:

- Business purpose: report writing, case library, quick scan, competitor tracking, or deep research.
- Preferred article types: case studies, deep analysis, data reports, interviews, official announcements, practical guides.
- Default quality bar: strict high-quality only, balanced, or broad background allowed.
- Default exclusions inferred by the AI from the user's answers: recruitment, courses, download bait, simple news recaps, low-value reposts, or similar low-value formats.
- Sparse-result behavior: accept fewer high-quality articles or allow core-related background articles.
- Default mode preference: `fast` for previews or `slow` for serious analysis.

Do not store one-off topics, private tokens, user credentials, or sensitive project details in local memory. If the file cannot be written, summarize the learned pattern in the conversation and apply it for the rest of the thread.

When running automatic mode, let `run_auto.ps1` read `research_memory.json` by default. Use `-NoMemory` only when the user explicitly wants to ignore local preferences for this run.

Ask only questions that materially change the result. If topic, count, time range, and user pattern are already inferable, do not ask; proceed to automatic mode.

Question pool:

1. What is the research topic and business purpose?
2. What time range should be included, and is it strict?
3. How many final articles are needed?
4. What does a good article look like for this task?
5. What kinds of articles feel low-value for this task? Infer concrete exclusions from the answer instead of forcing the user to list every exclusion.
6. If exact matches are sparse, should the result include core-related background articles or return fewer articles?

Useful optional questions:

- Is this topic about marketing, industry research, technology, policy, company strategy, product, finance, sports, or another field?
- Are specific brands, companies, people, accounts, or regions required?
- Are ambiguous meanings possible? For example, "外星人" could mean UFO, Ronaldo, or Alienware.
- Should the result favor case studies, deep analysis, data reports, interviews, official announcements, or practical guides?
- Should old but important articles be allowed?

## Defaults

When the user does not specify:

- Final count: 20 articles.
- Search mode: `slow`.
- Candidate pool: up to 2x final count in `fast`, up to about 3x final count in `slow`.
- Time range: ask once; if still unknown, use the automatic mode default: recent year.
- Screening mode: always use the project's general screening path.
- URL type: prefer original `mp.weixin.qq.com` article URLs.

## Search Planning

Build query groups from the user's intent:

- Core topic: the literal topic and key entities.
- Value queries: add `案例`, `复盘`, `拆解`, `分析`, `趋势`, `观察`, `洞察`, `报告`, `研究`, `策略`, `行业`.
- Time queries: add each year in the requested time range, such as `2025` and `2026`.
- Domain queries: add field-specific terms only when relevant.
- Disambiguation queries: add clarifying terms when a topic has multiple meanings.

Examples:

- Marketing topic: `{topic} 品牌营销`, `{topic} 营销案例`, `{topic} 投放`, `{topic} 消费者`.
- Industry topic: `{topic} 产业链`, `{topic} 行业分析`, `{topic} 商业化`, `{topic} 公司`.
- Technology topic: `{topic} 技术路线`, `{topic} 产品`, `{topic} 生态`, `{topic} 量产`.
- Policy topic: `{topic} 政策解读`, `{topic} 监管`, `{topic} 影响`, `{topic} 地方`.
- Ambiguous topic: combine the ambiguous word with the intended meaning, such as `外星人 Alienware 世界杯`, `外星人 罗纳尔多 世界杯`, or `外星人 UFO 世界杯`.

## Screening Rubric

Score qualitatively first, then numerically if needed.

Strong:

- Clearly answers the user's research need.
- Contains case details, analysis, data, examples, strategy, trend explanation, or useful context.
- Matches the requested time range and meaning of the topic.
- Comes from a relevant public account or a credible original source.
- Has a resolvable `mp.weixin.qq.com` URL.

Maybe:

- Related but narrow, short, old, or only partially aligned.
- Good source but weak title or thin abstract.
- Strong title but unclear article depth.
- Core-related context that would help the user write a report, even if it does not contain every intent word from the query.

Weak or reject:

- Only matches keywords but not the user's intent.
- Mostly news recap, notice, event announcement, schedule, live preview, recruitment, course promotion, download bait, listicle, or repost.
- Outside the time range.
- Ambiguous meaning is wrong.
- Broken, deleted, login-only, blocked, duplicate, or not a WeChat article.
- WeChat pages that say the content was deleted, unavailable, or cannot be viewed.

## Scoring Signals

Use multiple signals. Do not require all of them.

Positive signals:

- Direct topic match in title, abstract, or article body.
- Abstract contains case, analysis, report, trend, strategy, data, or specific examples.
- Search query that found the article included high-intent words such as `案例`, `复盘`, `研究`, `趋势`, `分析`.
- Account/source name suggests relevance: industry, research, data, business, technology, marketing, brand, policy, finance, or the user's field.
- The article is recent enough for the requested task.

Negative signals:

- Title or abstract contains low-value formats: `周报`, `榜单`, `官宣`, `通知`, `直播`, `报名`, `课程`, `资料包`, `下载`, `招聘`.
- Topic meaning is wrong.
- The date is outside the requested range.
- The article is a sports score/news recap when the user wants business, marketing, or analysis.
- The article is an SEO-like aggregation or repost without added value.

## Output

Return:

1. Clarified criteria used for screening.
2. The automatic-mode command to run, if the project scripts are available.
3. Search query groups used.
4. Candidate table with title, account/source, date, score or class, URL, and reason.
5. Final selected URLs, one per line.
6. Rejections or caveats, especially ambiguity, thin search results, old dates, or link-resolution failures.

When preparing input for MinerU, write only final verified `mp.weixin.qq.com` URLs to `urls.txt`.
