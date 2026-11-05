# 公共知识库语料来源

`samples/public/` 下的语料是**中文二次撰写的综述式笔记**，不是原文转载：只提炼结论与
可执行数字，并统一成本项目的写作风格（分节 + 编号条目 + 具体数值）。因此可随项目分发，
不受原文版权约束；引用源仅作事实核对依据。

> 维护方式：改完 `samples/public/*.md` 后，在 `scripts/corpus_manifest.py` 登记，
> 执行 `./.venv/Scripts/python.exe scripts/rebuild_public_kb.py` 重建向量库。

## 语料与依据对照

| 语料 | 主要依据 |
| --- | --- |
| 健身入门基础知识.md | [WHO 身体活动指南](https://www.who.int/publications/i/item/9789240015128)、[ACSM 抗阻训练进阶模型](https://www.sportgeneeskunde.com/files/bestanden/ACSM%20Position%20Stand%20Progression%20models%20in%20resistance%20training%20for%20healthy%20adults.pdf) |
| 减脂饮食原则.md | [ISSN 蛋白质与运动立场声明](https://pmc.ncbi.nlm.nih.gov/articles/PMC5477153/)、中国营养学会《中国居民膳食指南（2022）》 |
| 力量训练安全要点.md | ACSM 抗阻训练技术要点、运动医学常见损伤预防共识 |
| 有氧与力量训练的搭配.md | ACSM 运动测试与处方指南（第 11 版）、同期训练干扰效应研究 |
| 睡眠与恢复指南.md | [AASM 成人睡眠时长建议（≥7 小时）](https://aasm.org/advocacy/position-statements/adult-sleep-duration-health-advisory/) |
| 热身与拉伸方法.md | ACSM 热身与柔韧性训练建议、静态拉伸对力量表现影响的 meta 分析 |
| 训练与饮食常见误区.md | ISSN 立场声明综述、运动营养常见谣言辟谣汇编 |
| 增肌饮食基础.md | [ISSN 蛋白质与运动立场声明](https://pmc.ncbi.nlm.nih.gov/articles/PMC5477153/)、增肌期能量盈余研究 |
| 体重管理与代谢常识.md | WHO 腰围与 BMI 标准、代谢适应与维持期研究 |
| 训练强度与RIR自主调节.md | [NASM：RPE/RIR 自主调节](https://www.nasm.org/resource-center/blog/training/how-to-use-rpe-and-rir-to-autoregulate-client-training)、[Helms 等自主调节系统综述](https://pmc.ncbi.nlm.nih.gov/articles/PMC7810043/) |
| 增肌训练量与频率.md | [Schoenfeld 等训练量剂量-反应 meta 分析](https://pubmed.ncbi.nlm.nih.gov/27433992/)、[训练频率综述](https://rpstrength.com/blogs/podcasts/training-frequency-decoded-the-11-set-rule-every-lifter-should-know) |
| 力量进阶与周期化安排.md | [ACSM 抗阻训练处方立场声明（综述汇总）](https://europepmc.org/article/PMC/PMC12965823)、线性/双重进阶与 5/3/1 经典方案 |
| 居家与出差训练方案.md | 自重训练进阶研究、ACSM 抗阻训练立场声明 |
| 跑步与有氧进阶.md | ACSM 运动测试与处方指南、极化训练（80/20）研究、Tanaka 最大心率公式 |
| 运动补剂与证据等级.md | ISSN 肌酸/咖啡因/β-丙氨酸立场声明、国际奥委会运动营养共识 |
| 减脂期保肌策略.md | ISSN 减脂期营养立场声明、自然健美备赛能量可用性综述 |
| 间歇性禁食与进食窗口.md | 间歇性禁食与连续热量限制对照试验、ISSN 餐次频率综述 |
| 训练补水与电解质.md | [ACSM 运动与补液立场声明](https://www.acsm.org/)、NATA 补液共识 |
| 女性训练与生理周期.md | [ACSM 孕期运动指南](https://www.acsm.org/)、国际奥委会女性运动员共识 |
| 中老年力量训练与骨健康.md | [WHO 2020 身体活动指南](https://www.who.int/publications/i/item/9789240015128)、ACSM 老年人运动立场声明 |
| 运动损伤处理与康复.md | [BJSM：PEACE & LOVE 软组织损伤处理](https://bjsm.bmj.com/content/54/2/72)（[博客版](https://blogs.bmj.com/bjsm/2019/04/26/soft-tissue-injuries-simply-need-peace-love/)） |
| 体成分评估方法.md | WHO 腰围/BMI 标准、WS/T 428-2013 中国成人超重肥胖判定、DEXA/BIA 误差研究 |
| 运动习惯与心理调节.md | 行为改变与习惯养成研究、运动心理学依从性综述 |

## 写作约定

1. 每篇 650~800 字，分 3~4 节，每节 3~5 条编号条目，便于按 500 字切分后**每片仍自成一体**。
2. 数字给区间而非单一值，并写明适用条件（如"体脂较高者可接近 1%"）。
3. 只在确有共识时给结论；证据弱的写成"经验法则/证据有限"。
4. 避免与既有语料重复同一事实——同一数字出现多处会让检索在多个文档间摇摆，
   `tests/eval_set.json` 里这类题用 `expectDocs` 接受任一合法来源。
