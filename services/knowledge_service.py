from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from product_agent.domain import KnowledgeDocument
from product_agent.repositories import KnowledgeRepository


class KnowledgeService:
    """
    共享知识与后续 RAG 的统一入口。

    TODO(iter3-knowledge-service):
    当前定位:
    - 本类是“知识共享 / RAG”的产品层入口
    - 现在只提供保存和读取骨架，不直接绑定具体向量库

    待实现:
    1. 接入 chunking
       实现思路:
       - 以 report / paper brief / taxonomy summary 为输入
       - 按段落、标题或主题块拆分成 chunk

    2. 接入 embedding
       实现思路:
       - 给每个 chunk 生成 embedding
       - embedding 存储方案后置，不阻塞当前服务接口设计

    3. 支持按 topic / tag 检索
       实现思路:
       - 先做关键词过滤
       - 后续替换为“关键词 + 向量召回”的混合检索

    4. 支持来源标注
       实现思路:
       - 每个知识片段都保留 source_task_id / source_type / title
       - 让后续回答能引用知识来源
    """

    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def save_summary(self, *, title: str, content: str, source_task_id: str | None = None) -> KnowledgeDocument:
        """
        保存一份知识摘要文档。

        参数:
        - title: 文档标题
        - content: 文档正文或摘要
        - source_task_id: 来源任务，可为空

        返回:
        - KnowledgeDocument

        副作用:
        - 调用 knowledge repository 做一次写入

        组员实现提示:
        - 后续若接 chunking，应在 save 之前或之后触发 chunk pipeline
        """
        document = KnowledgeDocument(
            document_id=f"doc_{uuid4().hex[:12]}",
            title=title,
            source_task_id=source_task_id,
            content=content,
            metadata={"created_at": datetime.now(UTC).isoformat()},
        )
        return self.repository.save(document)

    def list_documents(self):
        """
        列出当前所有知识文档。

        当前用途:
        - 调试
        - 后续关键词召回的最小入口
        """
        return self.repository.list_all()
