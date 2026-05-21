# 上下文与 RAG 设计说明

这份文档回答三个问题：

1. 当前系统里的“上下文”到底有哪些层次
2. 现在的 `KnowledgeService` 到底做到哪了
3. 下一阶段如果要减少 fallback、提升多轮追问质量，后端应该怎么接 RAG

---

## 1. 当前为什么必须把这件事讲清楚

`product_agent/` 现在已经不是单轮脚本，而是：

- 有 `Conversation`
- 有多条 `Message`
- 有 follow-up task
- 有历史会话和历史任务
- 有 SQLite 持久化

这意味着系统已经具备“持续研究会话”的外形。  
但如果上下文和知识增强没有先定边界，后面就很容易出现：

- 每个接口各自拼上下文
- 会话历史和知识库混用
- RAG 被写死在某个节点里
- 前端以为“有 knowledge_service 就等于已经做完 RAG”

所以当前阶段虽然**不要求完整做完产品级 RAG**，但必须先把：

- 术语
- 数据结构
- 责任边界
- 接入时机

讲清楚。

---

## 2. 当前系统里的上下文分哪三层

建议统一把上下文分成三层。

### 2.1 当前轮输入

来源：

- 用户当前发送的消息
- 当前创建任务时填写的 topic / focus

作用：

- 决定本轮分析的直接目标

例子：

- “只看 evaluation benchmark”
- “关注 cost control”

### 2.2 会话级上下文

来源：

- 当前 `Conversation` 的历史消息
- 最近若干条 `Message`
- assistant 回写的任务结果摘要

作用：

- 让系统知道“这不是第一次问”
- 支持 follow-up task 生成
- 支持历史研究线索延续

当前现状：

- 已经有 `MessageService.get_recent_context(...)`
- 已经有 `continue_conversation`
- 已经能把任务执行结果回写为 assistant message

也就是说：

**会话级上下文已经开始真实存在，但当前仍偏轻量。**

### 2.3 外部知识上下文

来源：

- 历史任务沉淀下来的知识文档
- 用户后续导入的论文、摘要、笔记
- 未来向量检索召回的知识片段

作用：

- 减少从零开始分析
- 提高多轮对话一致性
- 减少 fallback 兜底论文出现的频率

当前现状：

- `KnowledgeService` 骨架已在
- SQLite 已支持 `knowledge_documents`
- 但主链路接入还不深

也就是说：

**知识层的“仓库和服务”有了，但用户目前还感知不到完整 RAG 能力。**

---

## 3. 当前代码里已经有什么

当前最重要的相关文件：

- [knowledge_service.py](/D:/iteration_two-master/iteration_two-master/product_agent/services/knowledge_service.py)
- [message_service.py](/D:/iteration_two-master/iteration_two-master/product_agent/services/message_service.py)
- [research_service.py](/D:/iteration_two-master/iteration_two-master/product_agent/services/research_service.py)
- [sqlite_store.py](/D:/iteration_two-master/iteration_two-master/product_agent/repositories/sqlite_store.py)

### 3.1 已经有的能力

- 保存知识摘要
- 关键词检索
- 向量检索骨架
- 检索入口 `retrieve(...)`
- SQLite 中保存 `knowledge_documents`

### 3.2 还没有完全接上的能力

- `continue_conversation` 没有真正读取知识库增强回复
- `create_task` / `run_task` 前没有先做知识召回
- 前端没有知识导入入口
- assistant 回答还没有显示“我参考了哪些历史知识”

所以现在更准确的说法不是“没做 RAG”，而是：

**RAG 基础设施草稿已存在，但主产品链路尚未接实。**

---

## 4. 当前最合理的 RAG 路线

### 第一阶段：会话上下文增强

目标：

- 先让“多轮会话”更像真的连续交流

做法：

- `continue_conversation` 读取最近若干条消息
- 必要时生成更短的会话摘要
- 把最近消息 + 摘要作为 follow-up task 的上下文输入

这一步的重点不是知识库，而是：

**让用户追问真正基于历史会话。**

### 第二阶段：结构化知识复用

目标：

- 减少 fallback
- 让旧研究结果能被复用

做法：

- 保存历史 task 的结构化摘要
- 按 topic / keyword / taxonomy branch 检索
- 在搜索或 synthesizer 之前先注入 retrieved knowledge

这一步不必一开始就上完整向量库，完全可以先用：

- keyword
- topic
- tag
- branch concept

做第一版。

### 第三阶段：向量检索 + rerank

目标：

- 提升召回质量
- 支持用户导入更多长文本材料

做法：

- chunk
- embedding
- vector search
- rerank

这一阶段再进一步把知识召回结果用于：

- search query refinement
- taxonomy grounding hint
- assistant final answer

---

## 5. 当前为什么还会出现 fallback

原因不是只有“搜索没搜到”，而是多种情况叠加：

- 检索源结果少
- 结果与 topic 对齐差
- taxonomy 分支过于理想化
- 知识库还没真正被用来兜底

所以现在的 `fallback` 更像：

- 一个工程兜底策略
- 保证 pipeline 不至于直接断

而不是一个真正令人满意的产品方案。

后续更合理的演进应该是：

1. 优先用历史知识或用户导入知识兜底
2. 其次再考虑系统 seed paper
3. 最后才暴露 fallback 状态给前端

---

## 6. 当前阶段的明确结论

### 已经完成

- Conversation / Message 主链路
- follow-up task 创建
- assistant 结果回写
- SQLite 持久化
- `KnowledgeService` 基础骨架

### 还没完成

- 用户可感知的 RAG
- 知识导入 UI
- 基于知识库的搜索增强
- 基于知识库的连续问答增强

---

## 7. 后端下一阶段具体任务

最适合后端组继续做的事情：

1. 在 `continue_conversation` 前加入知识召回
2. 在 `run_task` 前加入知识检索增强
3. 增加知识导入接口
4. 让 assistant 回复标出使用了哪些知识来源

建议新增或补强：

- `POST /knowledge/documents`
- `GET /knowledge/documents`
- `KnowledgeService.retrieve_for_conversation(...)`
- `KnowledgeService.retrieve_for_task(...)`

---

## 8. 一句话总结

当前系统已经有：

**会话历史 + follow-up task + knowledge service 骨架 + SQLite 持久化**

但还没有真正做到：

**“基于历史知识继续思考并回答”的产品级 RAG。**

下一阶段的正确方向不是重新发明一套架构，而是：

**把知识层真正接进 Conversation -> Task -> Workspace 这条主链。**
