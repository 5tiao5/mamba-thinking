# Product Agent

`product_agent/` 是迭代三的新主仓库。  
它的目标不是继续给旧 CLI 原型打补丁，而是把系统重构成一个更适合多人协作、前后端分离、逐步产品化的科研调研工作台。

## 当前仓库里有什么

- `api/`
  - FastAPI 路由与 handler
- `services/`
  - 产品级业务编排层
- `repositories/`
  - 数据存取边界，当前主实现是 InMemory
- `registries/`
  - tools / skills 注册与配置入口
- `schemas/`
  - 前后端接口合同
- `domain/`
  - 领域实体
- `research_agent/`
  - 研究分析主流程
- `ui/`
  - React + Vite 前端
- `docs/`
  - 架构、接口、分工、字段字典、时序图等文档

## 先看什么

如果你是第一次进入仓库，建议按这个顺序阅读：

1. [架构设计说明](D:/iteration_two-master/iteration_two-master/product_agent/docs/架构设计说明.md)
2. [前后端分工说明](D:/iteration_two-master/iteration_two-master/product_agent/docs/前后端分工说明.md)
3. [任务清单](D:/iteration_two-master/iteration_two-master/product_agent/docs/任务清单.md)
4. [接口与函数参考文档](D:/iteration_two-master/iteration_two-master/product_agent/docs/接口与函数参考文档.md)
5. [调用关系参考](D:/iteration_two-master/iteration_two-master/product_agent/docs/调用关系参考.md)

如果你负责多轮对话或知识增强，再补看：

- [消息链路说明](D:/iteration_two-master/iteration_two-master/product_agent/docs/消息链路说明.md)
- [上下文与RAG策略](D:/iteration_two-master/iteration_two-master/product_agent/docs/CONTEXT_RAG_STRATEGY.md)

## 本地启动

### 后端

```powershell
uvicorn product_agent.api.fastapi_app:app --reload
```

默认地址：

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### 前端

```powershell
cd ui
npm install
npm run dev
```

默认地址：

- Frontend: `http://127.0.0.1:5173`

## 开发边界

请默认遵守这几条：

1. 前端只依赖 FastAPI 接口和 `schemas/` 合同。
2. handler 不直接访问 repository。
3. 复杂业务逻辑优先放在 `services/`。
4. 研究分析主流程优先收敛在 `research_agent/`。
5. 新功能优先写进 `product_agent/`，不要继续往旧原型目录堆功能。

## 当前状态

已经真实可用的主链路：

- 创建会话
- 创建/读取消息
- 继续对话时写消息并创建 follow-up task
- 创建研究任务
- 运行研究任务
- 拉取 workspace 快照
- 查看 tools / skills

还在持续建设中的部分：

- 历史页接口
- 正式数据库持久化
- 完整 RAG / shared knowledge
- 更完整的 taxonomy / graph / trace 前端展示
- `auditor` / `synthesizer` 继续细拆成更清晰的内部 service

一句话理解当前仓库：

**它已经是一个可运行、可分工、可继续长大的工程基线，而不是只有概念图的脚手架。**
