---
name: wechat-article-screening
description: Question-led workflow for finding, screening, and selecting WeChat public-account articles. Use when an AI agent must turn a vague research need into an automatic-mode command, search queries, candidate scoring, clarified inclusion/exclusion rules, and final mp.weixin.qq.com URLs for tools such as MinerU. Suitable for marketing, industry, policy, company, technology, product, sports, and other WeChat article research topics.
---

# WeChat Article Screening

Use this skill to help a user find useful WeChat public-account articles, especially when the topic is broad or ambiguous. Work by asking the fewest useful questions, then turn the user's need into the project's automatic mode whenever the project scripts are available.

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
- Add `-StartDate` and `-EndDate` only when the user gave an explicit date range. If no date range is given, let `run_auto.ps1` use its default recent-year window.
- Add `-Focus marketing` only when the user clearly wants marketing, advertising, brand, sponsorship, campaign, media, or consumer insight articles. Otherwise omit it and let automatic mode use `general`.
- Add `-ExtraKeywords` only for important disambiguation terms, required entities, or exclusions that would be awkward to pack into the topic.
- Add `-OnlyUrls` only when the user wants to stop after generating `urls.txt` and not run MinerU.
- Use graded relevance. Prefer exact matches first, then articles that are useful for writing a report on the topic. If exact matches are sparse, include clearly useful core-related context instead of returning an unnecessarily tiny list.
- Keep runtime bounded. Do one automatic search pass with a screening pool no larger than `count * 2`; do not run extra search rounds just to force the final result to exactly match the requested count.

After asking clarifying questions, either run the command or show the exact command the user should run. Keep the command simple; do not expose low-level research parameters unless the user asks.

## Ask First

Ask only questions that materially change the result. Prefer 1 to 3 questions, and continue with defaults if the user does not know. If topic, count, and time range are already inferable, do not ask; proceed to automatic mode.

Question pool:

1. What is the exact research topic?
2. What time range should be included?
3. How many final articles are needed?
4. What does a good article look like for this task?
5. What should be excluded?

Useful optional questions:

- Is this topic about marketing, industry research, technology, policy, company strategy, product, finance, sports, or another field?
- Are specific brands, companies, people, accounts, or regions required?
- Are ambiguous meanings possible? For example, "外星人" could mean UFO, Ronaldo, or Alienware.
- Should the result favor case studies, deep analysis, data reports, interviews, official announcements, or practical guides?
- Should old but important articles be allowed?

## Defaults

When the user does not specify:

- Final count: 20 articles.
- Candidate pool: at most 2x final count.
- Time range: ask once; if still unknown, use the automatic mode default: recent year.
- Focus: use `general` unless the task clearly needs a field-specific mode.
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
