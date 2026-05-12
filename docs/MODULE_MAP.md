# 重构版模块地图

## 目标

本目录解决的是旧版 `graph.py` 主流程过于集中的问题。

## 当前拆分结果

- `product_agent/main.py`
  - 重构版运行入口
- `product_agent/research_agent/controller.py`
  - 只负责状态驱动决策
- `product_agent/research_agent/runtime.py`
  - 只负责执行循环、进度、action trace
- `product_agent/research_agent/pipeline.py`
  - 负责组装 action map 和流程入口
- `product_agent/research_agent/nodes/`
  - 每个节点单文件

## 节点职责

- `planner.py`
  - 生成 query 和 agent plan
- `searcher.py`
  - 检索论文并补齐候选
- `taxonomy.py`
  - 构建专家 taxonomy
- `evolution.py`
  - 构建论文演进边
- `auditor.py`
  - 审计结果质量
- `corrector.py`
  - 决定是否进行一次修正检索
- `synthesizer.py`
  - 输出报告、图谱和选题

## 后续继续重构的优先级

1. 把 `auditor.py` 拆成 taxonomy audit / graph audit / llm audit
2. 把 `synthesizer.py` 拆成 idea service / report service / graph render service
3. 把 `main.py` 的输出逻辑拆成 presentation 层
4. 在这个目录上继续搭建迭代三产品框架
