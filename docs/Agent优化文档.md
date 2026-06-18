# Agent 优化文档

更新时间：2026-06-18

本文记录 Product Agent 在迭代三产品化阶段的优化过程，包括问题发现、优化实现、优化后效果和评估数据位置。

## 1. 优化目标

本轮优化不以“功能数量”为核心，而以产品价值为核心：

1. 用户能通过系统找到有用论文。
2. 用户能理解为什么这些论文重要。
3. 用户能看到 taxonomy、图谱、空白和建议的证据边界。
4. 用户追问后系统会继续检索或重排，而不是只复述旧结果。
5. 系统能沉淀多轮研究，而不是每次从零开始。

最终目标是让 Product Agent 相比“直接问 AI”更有价值：

- 有真实论文证据池。
- 有用户上传 PDF 的利用能力。
- 有多轮工作台和研究总览。
- 有可追踪的 Agent 运行过程。
- 有结论证据等级和风险边界。

## 2. 优化前主要问题

### 2.1 检索与补搜问题

| 问题 | 影响 |
| --- | --- |
| 追问“近两年/近三年”后没有真正补搜 | 用户约束没有被系统执行 |
| 搜不到论文时容易出现 seed/fallback 论文 | 用户会误以为系统找到真实证据 |
| 新主题容易查不到或查偏 | 产品核心价值变弱 |
| 中英混输和随意表述不稳定 | 对用户输入要求过高 |

### 2.2 论文证据问题

| 问题 | 影响 |
| --- | --- |
| 引用数未知时显示为 `0` | 造成虚假确定性 |
| 用户上传论文来源表达不清楚 | 用户无法判断论文来自哪里 |
| 核心论文数量和选择依据不透明 | 用户不知道为什么先读这些论文 |
| 论文详情只有元数据或模板话术 | 对真实阅读帮助有限 |

### 2.3 结构化结论问题

| 问题 | 影响 |
| --- | --- |
| 研究空白和建议缺少证据等级 | 用户不知道建议是否可信 |
| taxonomy 分支显示论文数但详情丢失论文名 | 页面自相矛盾 |
| 演进图关系全是 related 或强关系过度自信 | 图谱产品价值不足 |
| 研究总览容易被最新一轮覆盖 | 多轮沉淀能力不明显 |

### 2.4 RAG 与上下文问题

| 问题 | 影响 |
| --- | --- |
| 共享知识可能污染当前研究 | 无关历史知识可能影响结论 |
| 命中片段像日志 | 用户不理解知识命中的意义 |
| 知识命中和论文证据边界不清 | 容易把参考上下文误认为已证实论文证据 |

### 2.5 用户体验问题

| 问题 | 影响 |
| --- | --- |
| 等待过程不透明 | 用户不知道系统是否卡住 |
| 工作台内容挤在一起 | 信息层级不清楚 |
| 追问后还要手动运行任务 | 对话闭环不自然 |
| 运行画板可能在结果刷新前提前收起 | 用户感觉生成流程不稳定 |

## 3. 优化实现

### 3.1 检索链路优化

实现内容：

- 引入通用 query decomposition，将用户输入拆成研究主题、目标、年份、方法、场景和重点概念。
- 增加 retrieval plan，把严格查询、宽查询、召回查询和 rerank signals 分开。
- 引入多源召回：
  - arXiv。
  - Semantic Scholar。
  - arXiv recall query。
  - 用户上传论文池。
- 对追问增加补搜策略：
  - 年份约束变化时补搜。
  - 新方法、新场景、新 focus facet 出现时补搜。
  - 扩展范围时补搜。
- 禁止用 seed/fallback 论文伪装成功。

相关文件：

- `research_agent/nodes/planner.py`
- `research_agent/nodes/searcher.py`
- `research_agent/retrieval_plan.py`
- `research_agent/relevance.py`
- `services/query_intent.py`

### 3.2 论文证据池优化

实现内容：

- 区分核心分析池和扩展证据池。
- 保留 `paper_source`、`source`、`source_channel` 等来源信息。
- 引用数增加 `citation_count_known` 标记，未知时显示“未获取”。
- 用户上传论文权重提高，不再轻易被系统检索论文冲掉。
- PDF 导入后尝试通过标题、DOI、arXiv 元数据反查补全引用、分类和外链。
- 合并总览时保留更完整元数据，避免追问后引用和来源丢失。

相关文件：

- `services/pdf_import_service.py`
- `services/research_paper_service.py`
- `research_agent/nodes/searcher.py`
- `services/workspace_service.py`

### 3.3 研究简报与论文详情优化

实现内容：

- 新增结构化 `research_brief`，减少旧 summary 的泛化文本。
- 核心论文卡片增加：
  - 做了什么。
  - 为什么先读。
  - 选择依据。
  - 来源与分类。
- Evidence 区论文详情增加阅读决策面板：
  - 阅读决策。
  - 适合支撑。
  - 读的时候问。
  - 不要误用。
- 新增 `paper_brief` 和 claim checks。
- 对用户上传 PDF 的正文片段做页码/章节感知 claim verification 初版。
- 可选启用轻量 LLM 改写研究简报和论文详情展示文本。

相关文件：

- `services/workspace_service.py`
- `services/paper_brief_llm_service.py`
- `services/claim_verification_service.py`
- `ui/src/components/research/ResearchPaperPanel.tsx`

### 3.4 结论准入契约优化

实现内容：

- 研究空白和研究建议必须保留：
  - `supporting_paper_ids`
  - `evidence_level`
  - `evidence_reason`
- 直接证据不足时，前端显示为探索性或待验证，而不是包装成已证实结论。
- RAG 命中不会自动变成论文证据。
- taxonomy、graph、gaps、ideas 都由后端负责证据判断，前端只展示。

相关文件：

- `research_agent/nodes/auditor.py`
- `research_agent/nodes/synthesizer.py`
- `services/taxonomy_grounding_service.py`
- `services/taxonomy_audit_service.py`
- `services/workspace_service.py`

### 3.5 演进图优化

实现内容：

- 图谱关系从单一 related 扩展为引用、改进、扩展、互补、评测范围扩展、主题关联等。
- 强关系必须有引用、正文片段或较强语义证据。
- 普通主题相似只作为候选线索，不包装成演进结论。
- 前端图谱节点大小融合引用数与连接度。
- 图谱支持按关系类型和分类筛选。
- 优化边曲率、节点布局和箭头观感。

相关文件：

- `research_agent/nodes/evolution.py`
- `services/relationship_evidence_service.py`
- `ui/src/components/research/ResearchGraph.tsx`

### 3.6 RAG 与共享知识优化

实现内容：

- 明确三种知识范围：
  - `none`
  - `conversation_only`
  - `shared`
- shared 只包含全局共享知识和当前研究私有知识，不泄漏其他研究私有知识。
- Context 区区分：
  - 当前研究资料命中。
  - 全局共享知识命中。
  - 对话继承和 working memory。
- 低相关共享知识被过滤。
- 前端提示 RAG 只辅助理解上下文，不替代论文证据。

相关文件：

- `services/knowledge_service.py`
- `services/research_service.py`
- `services/working_memory_service.py`
- `ui/src/components/research/WorkspaceContextPanel.tsx`

### 3.7 Agent 运行可视化优化

实现内容：

- 新增 task events，用于记录 Agent 运行过程。
- 前端等待状态从纯 loading 改为 Agent Node 运行图。
- 节点包括 Planner、Searcher、Taxonomy、Evolution、Auditor、Corrector、Synth、Result。
- 节点和边可显示重复运行次数。
- 运行结束后，等待画板在历史和结果刷新完成后再自动收起。

相关文件：

- `repositories/sqlite_store.py`
- `services/research_service.py`
- `api/handlers.py`
- `ui/src/components/chat/AgentRunGraph.tsx`
- `ui/src/components/layout/AppShell.tsx`

## 4. 优化后效果

### 4.1 产品闭环更完整

用户现在可以完成：

```text
新建研究 -> 可选导入 PDF -> 选择研究方式 -> 生成结果
-> 查看论文证据、研究结构、知识上下文和运行轨迹
-> 继续追问 -> 自动生成新结果 -> 查看本研究总览
```

### 4.2 证据边界更清楚

优化后系统会明确区分：

- 系统检索论文。
- 用户上传论文。
- 当前研究私有知识。
- 全局共享知识。
- 扩展证据池。
- 核心分析池。
- 直接证据、间接证据和待验证假设。

### 4.3 追问链路更自然

追问后默认创建并运行 follow-up task，用户不需要再手动点一次运行。等待过程中能看到 Agent 状态，任务完成后会自动刷新到对应结果。

### 4.4 答辩解释性更强

系统不只展示最终文本，还能解释：

- 为什么搜这些词。
- 为什么选这些论文。
- 图谱关系凭什么成立。
- 哪些建议证据强，哪些只是探索性方向。
- RAG 命中只是上下文还是论文证据。

## 5. 评估方式

### 5.1 检索质量评测

数据集：

- `evaluation/retrieval_cases.json`

说明文档：

- [检索质量评测说明](检索质量评测说明.md)

运行方式：

```powershell
cd D:\product_agent
python .\evaluation\retrieval_quality.py --validate-only
python .\evaluation\retrieval_quality.py
```

历史输出：

- `outputs/retrieval_eval/`

### 5.2 主链质量验收

数据集：

- `evaluation/main_chain_cases.json`

说明文档：

- [主链质量验收说明](主链质量验收说明.md)

覆盖主题包括：

- AI Agent 工具使用评测。
- 大模型多模态融合。
- AI Agent for Software Engineering。
- PDF + 混合研究。
- 共享知识污染边界。
- 通信计算 overlap 自动编排。

### 5.3 自动化测试

后端测试集中覆盖：

- query decomposition。
- 检索质量门禁。
- paper relevance。
- workspace paper merge。
- PDF import。
- paper brief。
- task events。
- runtime config。
- knowledge delete cascade。

运行方式：

```powershell
python -m pytest
```

前端构建验证：

```powershell
cd D:\product_agent\ui
npm run build
```

## 6. 当前仍存在的风险

| 风险 | 当前处理 | 后续建议 |
| --- | --- | --- |
| 外部论文 API 限流 | 记录降级状态，避免伪装成功 | 增加缓存和 S2 API key 配置 |
| 全文 claim verification 成本较高 | 先做片段级核查 | 对核心论文并行逐篇分析 |
| Skill 仍是策略模板 | 已有 CRUD 和任务选择 | 如果时间不足，不作为核心演示卖点 |
| 演进图强关系可能偏少 | 保守准入 | 用“可信图谱”而非“热闹图谱”解释 |
| 研究总览语义融合仍可增强 | 已做字段合并和近期权重 | 后续可增加更强 LLM 合并层 |

## 7. 结论

本轮优化的核心成果是：Product Agent 已从“能跑的科研助手 Demo”提升为“有证据池、有多轮沉淀、有运行可视化、有结论边界的科研调研工作台”。

后续如果继续投入，应优先优化：

1. 检索质量和补搜稳定性。
2. 核心论文详情和全文 claim verification。
3. 研究总览的多轮语义融合。
4. 固定主链演示和评测数据记录。

