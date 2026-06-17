# Product Agent UI Workspace

本目录承接迭代三前端实现，技术栈已确定为：

- React
- Vite
- TypeScript
- React Router

## 本地启动

安装依赖：

```powershell
cd product_agent/ui
npm install
```

启动开发服务器：

```powershell
npm run dev
```

默认前端地址：

- `http://127.0.0.1:5173`

默认后端地址：

- `http://127.0.0.1:8001`

如果后端地址变动，可在 `.env.local` 中设置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

## 页面规划

- `/`
  - 新建研究会话 + 最近任务入口
- `/conversation`
  - 多轮对话区
- `/workspace`
  - 研究工作台
- `/history`
  - 历史会话
- `/settings`
  - 工具和 skill 管理

## 前端同学优先任务

1. 跑通页面路由
2. 对接新建会话与创建任务接口
3. 做 workspace 布局
4. 对接工具 / skill 列表
