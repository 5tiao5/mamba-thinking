import { Link } from "react-router-dom";

import { SectionHeader } from "../components/ui/SectionHeader";
import { StatusPill } from "../components/ui/StatusPill";

const savedFilters = ["全部", "进行中", "已完成", "已收藏"];

export function HistoryPage() {
  return (
    <div className="dense-layout">
      <section className="surface content-pad history-toolbar">
        <label>
          <span className="field-label">搜索研究记录</span>
          <input className="input" placeholder="按主题、论文、研究空白或选题关键词搜索" />
        </label>
        <div>
          <span className="field-label">状态筛选</span>
          <div className="button-row">
            {savedFilters.map((filter) => (
              <button className={filter === "全部" ? "primary-button" : "secondary-button"} key={filter} type="button">
                {filter}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="pane">
        <SectionHeader
          actions={<StatusPill tone="neutral">暂无记录</StatusPill>}
          title="历史研究"
          eyebrow="Saved work"
        />
        <div className="content-pad content-grid">
          <div className="empty-state">
            这里会集中保存你完成过的研究会话和工作台结果。完成一次研究后，可以从这里继续会话、回看论文线索，
            或重新打开工作台继续整理研究空白和选题建议。
          </div>
          <div className="button-row">
            <Link className="primary-button" to="/">
              新建研究
            </Link>
            <Link className="secondary-button" to="/conversation">
              继续对话
            </Link>
            <Link className="ghost-button" to="/workspace">
              打开工作台
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
