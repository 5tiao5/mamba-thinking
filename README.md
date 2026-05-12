# Product Agent Refactor Workspace

这个目录用于承接迭代三的彻底重构工作，目标是：

- 不再继续堆叠旧版原型代码
- 在新目录中完成主流程模块化
- 保留现有能力，逐步迁移到更适合多人协作的结构

当前阶段已经完成：

- 把旧版 `graph.py` 的核心流程拆成 `controller + runtime + nodes`
- 提供了新的运行入口 `product_agent/main.py`
- 保留与旧版工具层、审计层、综合输出层的兼容

推荐运行方式：

```powershell
python -m product_agent.main "AI Agent Tool Use" --fast --output-dir product_agent_outputs
```

如果要启动迭代三后端骨架：

```powershell
uvicorn product_agent.api.fastapi_app:app --reload
```

本目录的定位是：

`先重构原型，再在这个重构版之上继续搭建迭代三产品框架。`
