"""文档管理 API 测试。"""

import contextlib
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state


def _patched_create_engine(*args, **kwargs):
    """对 SQLite 内存数据库使用 StaticPool，确保多线程共享连接。"""
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client():
    """提供已认证的 TestClient。"""
    cm_vector = patch("comedy_agent.api.server.VectorStore")
    cm_retriever = patch("comedy_agent.api.server.ComedyRetriever")
    cm_graph = patch("comedy_agent.api.server.build_chat_graph")

    with cm_vector, cm_retriever, cm_graph, patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = []
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")

            c.post("/auth/register", json={"user_id": "admin", "password": "testpass"})
            login_resp = c.post("/auth/login", json={"user_id": "admin", "password": "testpass"})
            token = login_resp.json()["access_token"]

            with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as authed_c:
                state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
                yield authed_c

    state.orch = None
    state.memory = None


@pytest.fixture
def temp_doc():
    """创建一个临时文本文件用于上传测试。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("这是一个喜剧理论测试文档。\n铺垫和笑点是喜剧的核心结构。\n")
        path = f.name
    yield path
    os.unlink(path)


class TestDocumentAPI:
    """文档上传/列表/删除 API 测试。"""

    def test_upload_and_list_documents(self, client, temp_doc):
        """测试上传文档后能够正确列出。"""
        with patch("comedy_agent.api.server.KnowledgeIngestor") as mock_ingestor_cls:
            mock_ingestor = MagicMock()
            mock_ingestor.ingest_file.return_value = {"raw_docs": 1, "chunks": 3, "ingested": 3}
            mock_ingestor_cls.return_value = mock_ingestor

            with open(temp_doc, "rb") as f:
                res = client.post(
                    "/documents/upload",
                    files={"files": ("theory_test.txt", f, "text/plain")},
                    data={"kind": "standup", "style": "traditional", "chunk_strategy": "scene", "topic": "职场加班"},
                )
            assert res.status_code == 200, res.text
            data = res.json()
            assert len(data) == 1
            assert data[0]["filename"] == "theory_test.txt"
            assert data[0]["status"] == "ingested"
            assert data[0]["chunks"] == 3
            assert data[0]["kind"] == "standup"
            assert data[0]["style"] == "traditional"
            assert data[0]["chunk_strategy"] == "scene"
            assert data[0]["topic"] == "职场加班"
            # 验证 ingestor 使用了正确的分块策略
            mock_ingestor_cls.assert_called_once()
            call_kwargs = mock_ingestor_cls.call_args.kwargs
            assert call_kwargs.get("chunk_strategy") == "scene"
            mock_ingestor.ingest_file.assert_called_once()
            ingest_file_args = mock_ingestor.ingest_file.call_args
            assert ingest_file_args.kwargs.get("kind") == "standup"
            assert ingest_file_args.kwargs.get("style") == "traditional"

        # 列出文档
        res2 = client.get("/documents")
        assert res2.status_code == 200
        docs = res2.json()["documents"]
        matched = [d for d in docs if d["filename"] == "theory_test.txt"]
        assert len(matched) == 1
        assert matched[0]["kind"] == "standup"
        assert matched[0]["style"] == "traditional"
        assert matched[0]["chunk_strategy"] == "scene"

    def test_delete_document(self, client, temp_doc):
        """测试删除文档后列表中不再出现。"""
        with patch("comedy_agent.api.server.KnowledgeIngestor") as mock_ingestor_cls:
            mock_ingestor = MagicMock()
            mock_ingestor.ingest_file.return_value = {"raw_docs": 1, "chunks": 2, "ingested": 2}
            mock_ingestor_cls.return_value = mock_ingestor

            with open(temp_doc, "rb") as f:
                res = client.post(
                    "/documents/upload",
                    files={"files": ("to_delete.txt", f, "text/plain")},
                )
        assert res.status_code == 200
        doc_id = res.json()[0]["doc_id"]

        with patch("comedy_agent.api.server.VectorStore") as mock_vs_cls:
            mock_vs = MagicMock()
            mock_vs.get_by_filter.return_value = []
            mock_vs_cls.return_value = mock_vs

            res_del = client.delete(f"/documents/{doc_id}")
            assert res_del.status_code == 200

        res_list = client.get("/documents")
        docs = res_list.json()["documents"]
        assert not any(d["doc_id"] == doc_id for d in docs)
