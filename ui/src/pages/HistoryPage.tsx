import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";

export function HistoryPage() {
  return (
    <div className="dense-layout">
      <section className="pane">
        <SectionHeader
          actions={<StatusPill tone="warning">backend pending</StatusPill>}
          title="历史任务与会话列表"
          eyebrow="History"
        />
        <div className="content-pad content-grid">
          <div className="empty-state">
            当前后端文档明确尚未提供 `GET /conversations` 和 `GET /research/tasks`，因此本页暂不做假数据列表。
            待后端补齐历史查询接口后，可在这里接入会话列表、最近任务和继续会话入口。
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Needed API</th>
                <th>Purpose</th>
                <th>Frontend Use</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <code>GET /conversations</code>
                </td>
                <td>查询会话历史</td>
                <td>继续会话、查看最新任务</td>
              </tr>
              <tr>
                <td>
                  <code>GET /research/tasks</code>
                </td>
                <td>查询最近研究任务</td>
                <td>打开 workspace、查看任务状态</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
