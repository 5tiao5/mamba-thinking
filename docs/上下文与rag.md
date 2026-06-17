# 上下文与 RAG 设计说明

更新时间：2026-06-15

本文描述当前已经运行的上下文与知识链路，而不是未来设计草案。

## 1. 核心原则

系统必须区分三件事：

1. **对话上下文**：帮助理解用户现在想研究什么。
2. **知识命中**：给模型提供可参考的外部材料。
3. **论文证据**：进入当前分析池、可支撑 taxonomy、图谱和结论的论文。

最重要的产品边界是：

**知识命中不自动等于论文证据，模型读到一段资料也不意味着该资料已经证明最终结论。**

## 2. 当前上下文组成

### 2.1 当前轮输入

包括：

- 当前研究主题或追问。
- 运行模式。
- 研究方式：`hybrid / imported_only / search_only`。
- 知识范围：`none / conversation_only / shared`。
- 用户选择的 `selected_skill_ids`。

当前轮输入决定本轮直接目标和检索约束。

### 2.2 会话历史

包括：

- 当前 conversation 的近期用户消息。
- assistant 回写的历史任务结果。
- 触发本轮任务的 message。

用途：

- 判断追问是扩大、缩小、比较还是继续展开。
- 继承年份、方法、场景等约束。
- 生成 follow-up task。

### 2.3 历史研究结果

包括：

- 之前 task workspace 的摘要。
- 历史 taxonomy 分支和研究空白。
- 高价值论文线索。
- conversation 总 workspace 提取的 hints。

这些内容通过 `inherited_context` 和研究上下文 bundle 进入后续任务。

### 2.4 Working Memory

working memory 是 conversation 级显式记忆，主要记录：

- `current_focus`：当前研究焦点。
- `summary`：多轮研究压缩摘要。
- `stable_findings`：相对稳定的发现。
- `open_questions`：尚未解决的问题。
- `active_constraints`：年份、方法、对象等活动约束。
- `supporting_task_ids`：形成这份记忆的任务。

它的作用是维持研究连续性，不负责替代论文证据。

### 2.5 外部知识

来源包括：

- 当前研究中用户上传的 PDF。
- 通过标题、DOI、arXiv ID 或链接导入的论文候选。
- 用户手动录入的摘要、笔记和资料。
- 共享知识库中的全局文档。
- 历史任务沉淀的知识文档。

知识范围语义：

| 范围 | 含义 |
| --- | --- |
| `none` | 不使用知识库增强 |
| `conversation_only` | 只使用当前研究资料 |
| `shared` | 使用当前研究资料和全局共享知识 |

## 3. 当前 RAG 流程

当前主链不是简单地把所有文档拼进 prompt，而是：

1. 根据研究主题、追问和历史上下文形成检索 query。
2. 对知识文档执行 chunk 级检索。
3. 将 chunk 命中聚合回文档。
4. 计算文档相关性和证据等级。
5. 过滤低相关或越界的共享知识。
6. 将保留结果作为 `knowledge_hits` 注入研究上下文。
7. 在 workspace 的 `source_trace` 中记录检索状态和命中来源。

知识命中字段包括：

- `title`
- `snippet`
- `scope`
- `source_type`
- `source_task_id`
- `score`
- `evidence_level`
- `matched_chunk_count`
- `supporting_snippets`

前端展示这些字段时，应使用“命中、参考、上下文”等措辞，不应写成“该资料已经证明结论”。

## 4. 论文导入链路

### 4.1 PDF 批量导入

接口：

`POST /conversations/{conversation_id}/papers/import-pdfs`

当前规则：

- 一次最多 10 篇。
- 单篇不超过 20 MB。
- 默认最多解析 80 页。
- 单篇失败不影响批次内其他文件。
- 解析结果同时形成当前研究论文资产和 conversation 范围知识文档。
- 创建研究前选择的 PDF 会在 conversation 创建后导入，但不会自动运行研究任务。

### 4.2 论文候选导入

用户可输入：

- 论文标题。
- DOI。
- arXiv ID。
- arXiv 链接。

后端识别候选后，用户可导入到：

- 当前研究。
- 全局共享知识。

候选导入主要补充元数据和摘要；它与上传全文 PDF 的信息完整度不同。

## 5. 知识如何进入首轮和追问

### 首轮研究

使用：

- 用户输入的研究主题。
- 创建研究前导入的 PDF。
- 当前研究论文池。
- 选定范围内的知识命中。
- 选中的 Skill 描述。

### 后续追问

在首轮基础上增加：

- 当前追问文本。
- 近期用户消息。
- 已有 workspace 摘要和研究 hints。
- working memory。
- 当前 conversation 已导入论文。

如果追问要求新年份、新方法或扩大覆盖范围，检索策略应尝试补搜；不能只从旧核心论文中重新挑选。

## 6. 论文证据与结论准入

RAG 命中经过上下文过滤后，仍不能直接支撑 gaps / ideas。结论证据遵循：

- `supporting_paper_ids` 只能引用当前 workspace 分析论文池中的论文。
- 外部共享知识中出现的论文 ID 若未进入分析池，会被丢弃。
- `direct`：有明确直接证据声明。
- `indirect`：与当前论文相关，但尚未完成全文级结论核验。
- `exploratory`：没有合格论文绑定，只能作为待验证假设。

前端会显示证据等级、绑定论文数、论文标题和 `evidence_reason`。

## 7. 当前仍存在的限制

- 知识命中尚缺少稳定的全文详情入口。
- PDF 元数据可能不完整，需要继续补全标题、作者、日期和外链。
- 共享知识仍可能出现语义相关但对当前问题无用的命中。
- embedding、rerank 和关键词策略仍需通过固定 bad case 校准。
- assistant 自然语言回复中的逐条引用仍弱于 workspace 的结构化证据展示。
- 全文级 graph 强关系识别覆盖率仍有限。

## 8. 下一阶段

1. 提供知识文档详情或全文查看。
2. 建立共享知识污染回归集。
3. 记录每轮知识过滤数量、命中数量和实际采用数量。
4. 将 query decomposition 的约束覆盖结果写入 trace。
5. 增强全文论文证据对 graph 和结论的支撑。

## 9. 一句话总结

**当前系统已经具备可运行的会话上下文、working memory、论文导入和 RAG；下一步重点是让知识来源更可查看、过滤更可靠、证据边界更容易被用户理解。**
