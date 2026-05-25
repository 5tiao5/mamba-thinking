# Product Agent

`product_agent/` 是迭代三的独立主仓库。  
它的目标不是继续给旧 CLI 原型打补丁，而是把系统重构成一个更适合多人协作、前后端分离、逐步产品化的科研调研工作台。

## 快速判断

如果你是第一次进入仓库，先记住这几句话：

- 当前已经跑通最小主链路：创建会话 -> 发送消息 -> 创建研究任务 -> 运行任务 -> 读取 workspace
- 当前前后端都能启动，SQLite 持久化默认可用
- 当前已经支持历史会话、历史任务、知识导入 API、会话级总 workspace 聚合接口
- 当前 taxonomy 和 graph 已经能展示，但“证据不足模式”“知识累积增强”仍在继续完善
- 当前最适合做的是沿着现有接口和 schema 继续做实，不要随意改结构边界

## 当前仓库结构

- `api/`
  - FastAPI 路由与 handler
- `services/`
  - 产品级业务编排层
- `repositories/`
  - 数据存取边界，当前支持 InMemory 与 SQLite
- `schemas/`
  - 前后端接口合同
- `domain/`
  - 领域实体
- `research_agent/`
  - 研究分析主流程
- `ui/`
  - React + Vite 前端
- `docs/`
  - 架构、接口、分工、字段字典、时序图、消息链路等文档

## 先看什么

建议按这个顺序阅读：

1. [架构设计说明](/D:/iteration_two-master/iteration_two-master/product_agent/docs/架构设计说明.md)
2. [前后端分工说明](/D:/iteration_two-master/iteration_two-master/product_agent/docs/前后端分工说明.md)
3. [任务清单](/D:/iteration_two-master/iteration_two-master/product_agent/docs/任务清单.md)
4. [接口与函数参考文档](/D:/iteration_two-master/iteration_two-master/product_agent/docs/接口与函数参考文档.md)
5. [调用关系参考](/D:/iteration_two-master/iteration_two-master/product_agent/docs/调用关系参考.md)

如果你负责多轮对话、知识增强或 workspace 聚合，再补看：

- [消息链路说明](/D:/iteration_two-master/iteration_two-master/product_agent/docs/消息链路说明.md)
- [上下文与rag](/D:/iteration_two-master/iteration_two-master/product_agent/docs/上下文与rag.md)
- [主链路时序图](/D:/iteration_two-master/iteration_two-master/product_agent/docs/主链路时序图.md)

## 本地启动

### 1. 先准备 `.env`

实际使用时，`.env` 要放在这里：

- [product_agent/.env](/D:/iteration_two-master/iteration_two-master/product_agent/.env)

不要放在外层大目录。  
后端现在会自动读取 `product_agent/.env`，不会默认去读外层 `.env`。

第一次可以这样准备：

```powershell
cd D:\iteration_two-master\iteration_two-master\product_agent
Copy-Item .env.example .env
```

然后按需填写：

```env
OPENAI_API_KEY=your-key-here
DEEPSEEK_API_KEY=your-key-here
```

更详细说明见：

- [本地环境变量说明](/D:/iteration_two-master/iteration_two-master/product_agent/docs/本地环境变量说明.md)

### 2. 启动后端

推荐直接在仓库根目录运行：

```powershell
cd D:\iteration_two-master\iteration_two-master\product_agent
python .\start_backend.py
```

可选：

```powershell
python .\start_backend.py --port 8001
python .\start_backend.py --no-reload
```

默认地址：

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### 3. 启动前端

```powershell
cd D:\iteration_two-master\iteration_two-master\product_agent\ui
npm install
npm run dev
```

默认地址：

- Frontend: [http://127.0.0.1:5173](http://127.0.0.1:5173)

## 当前已经真实可用的功能

后端：

- 创建会话、会话列表、会话详情
- 创建消息、读取消息列表
- `continue_conversation` 生成 follow-up task
- 创建任务、任务列表、任务详情、运行任务
- 读取 task 级 workspace
- 读取 conversation 级总 workspace
- 读取与导入 knowledge documents
- 默认 SQLite 持久化

前端：

- 首页能创建会话
- 对话页能读消息、追问、运行 follow-up task、跳转工作台
- 工作台能看 summary / taxonomy / papers / graph / gaps / ideas / trace
- 历史页已能读真实会话与任务数据
- 设置页已能展示 tools / skills

## 当前仍在继续建设的重点

- 证据不足模式下的更自然展示与后续引导
- taxonomy / graph 的继续打磨
- knowledge 导入后的真正 retrieval 接入
- conversation 级总 workspace 的持续增强
- 多轮会话里更自然的 assistant 回答体验
- 更正式的 CI/CD 与部署链路

## 开发边界

请默认遵守这些规则：

1. 前端只依赖 FastAPI 接口和 `schemas/` 合同
2. handler 不直接访问 repository
3. 复杂业务逻辑优先放在 `services/`
4. 研究分析主流程优先收敛在 `research_agent/`
5. 所有新功能优先继续写进 `product_agent/`

## 当前状态一句话总结

**它已经是一套可运行、可分工、可继续长大的工程基线，可以进入下一阶段的多人并行开发。**

## 前端分支同步提醒

如果前端同学当前在单独的前端分支上继续开发，请先同步本轮后端改动，再继续做页面与交互。

这轮后端已经升级了 `workspace / taxonomy / evidence_status` 的返回结构，前端如果继续使用旧 mock 数据或旧类型，很容易出现：

- `npm run build` 失败
- taxonomy 区域字段缺失
- evidence-insufficient 模式展示不完整
- workspace 组件读取旧字段导致显示异常

前端同学同步分支后，优先检查这些文件：

1. [api.ts](/D:/iteration_two-master/iteration_two-master/product_agent/ui/src/types/api.ts)
2. [demoData.ts](/D:/iteration_two-master/iteration_two-master/product_agent/ui/src/lib/demoData.ts)
3. [WorkspacePage.tsx](/D:/iteration_two-master/iteration_two-master/product_agent/ui/src/pages/WorkspacePage.tsx)
4. [WorkspaceTaxonomyRail.tsx](/D:/iteration_two-master/iteration_two-master/product_agent/ui/src/components/workspace/WorkspaceTaxonomyRail.tsx)
5. [WorkspaceTaxonomyMap.tsx](/D:/iteration_two-master/iteration_two-master/product_agent/ui/src/components/workspace/WorkspaceTaxonomyMap.tsx)

这轮前端需要重点适配的字段包括：

- `WorkspaceTaxonomyBranch.evidence_tier`
- `WorkspaceTaxonomyBranch.branch_confidence`
- `WorkspaceTaxonomyBranch.matched_paper_ids`
- `WorkspaceTaxonomyBranch.matched_gap_ids`
- `taxonomy.coverage[branch_id].evidence_tier`
- `workspace.evidence_status.*`

## .env 放置位置

后端现在会自动读取仓库内的 `.env` 文件，正确位置是：

- [product_agent/.env](/D:/iteration_two-master/iteration_two-master/product_agent/.env)

不是外层目录，也不是 `ui/` 目录。

建议组员第一次启动前，先在 `product_agent/` 目录里执行：

```powershell
cd D:\iteration_two-master\iteration_two-master\product_agent
Copy-Item .env.example .env
```

然后把自己的 API key 填进去，再启动后端：

```powershell
python .\start_backend.py
```
