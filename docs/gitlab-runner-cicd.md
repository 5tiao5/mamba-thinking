# GitLab Runner CI/CD 说明

## 目标

本项目使用本地虚拟机上的 GitLab Runner 执行 CI/CD。默认分支每次提交都会触发流水线：后端验证、前端构建、默认分支镜像同步。GitHub mirror 更新后，由 Vercel 自动部署前端，由 Render 自动部署后端。

## Runner 配置

- Runner 类型：本地虚拟机 GitLab Runner。
- Runner tag：`course-runner`。
- Pipeline 文件：仓库根目录 `.gitlab-ci.yml`。
- 依赖镜像：Python 使用清华 PyPI 镜像，npm 使用 npmmirror。

## Pipeline 阶段

1. `backend_tests`
   - 创建 Python 虚拟环境。
   - 安装 `requirements.txt` 和 `pytest`。
   - 执行 `compileall`。
   - 导入 FastAPI app，确认后端应用可加载。
   - 执行 `python -m pytest`。

2. `frontend_build`
   - 进入 `ui/`。
   - 执行 `npm ci --cache .npm --prefer-offline`。
   - 执行 `npm run build`。
   - 保存 `ui/dist` 为 7 天 artifact。

3. `deploy_mirror`
   - 只在默认分支执行。
   - 依赖后端测试和前端构建成功。
   - 将当前提交推送到 GitHub mirror。
   - 生成 `CI_DEPLOY_INFO.txt`，保存 30 天。

## GitLab CI/CD 变量

必须在 GitLab 项目 Settings -> CI/CD -> Variables 中配置：

- `GITHUB_MIRROR_URL`：GitHub mirror 的推送地址，建议使用 masked/protected 变量保存 token 或 SSH 地址。

可选变量：

- `GITHUB_MIRROR_BRANCH`：GitHub mirror 目标分支；未配置时使用 GitLab 默认分支名。

部署平台变量：

- Vercel 前端需要配置 `VITE_API_BASE_URL`，值为 Render 后端地址。
- Render 后端需要配置 `PRODUCT_AGENT_CORS_ORIGINS`，值为允许访问后端的前端域名，多个域名用英文逗号分隔。

## 验收记录

课程验收时建议保留以下证据：

- GitLab Pipelines 页面中的流水线记录。
- `frontend_build` 的 `ui/dist` artifact。
- `deploy_mirror` 的 `CI_DEPLOY_INFO.txt` artifact。
- GitHub mirror 上对应 commit。
- Vercel 和 Render 的自动部署记录。
