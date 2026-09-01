from __future__ import annotations

import hashlib
import json
from typing import Any

from shared.evidence.base_card import BaseEvidenceCard


CARD_TABLE = "evidence_cards"


class CardStore:
    """LanceDB-backed evidence card store with hybrid vector + scalar search.

    Falls back to a JSONL on-disk store if LanceDB is unavailable, so the system
    can run in stub/offline mode during early development.
    """

    def __init__(self, project_id: str, use_lancedb: bool = True) -> None:
        from shared.core.config import settings
        self.project_id = project_id
        self.db_dir = settings.l1_warm_dir / project_id
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._fallback_path = self.db_dir / "cards.jsonl"
        self._fallback_rows: list[dict[str, Any]] = []
        self._keys: set[str] = set()
        self._db = None
        self._table = None
        if use_lancedb:
            self._init_lancedb()
        if self._table is None:
            self._load_fallback()
            self._keys = {self._dedup_key(r) for r in self._fallback_rows}
            # 载入时自动去重并回写，保证磁盘与内存一致
            if len(self._keys) < len(self._fallback_rows):
                self.dedup_existing()

    def _init_lancedb(self) -> None:
        try:
            import lancedb

            self._db = lancedb.connect(str(self.db_dir))
            existing = self._db.table_names() if hasattr(self._db, "table_names") else []
            if CARD_TABLE in existing:
                self._table = self._db.open_table(CARD_TABLE)
        except Exception:
            self._db = None

    def _load_fallback(self) -> None:
        if self._fallback_path.exists():
            for line in self._fallback_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    self._fallback_rows.append(json.loads(line))

    def _fallback_append(self, row: dict[str, Any]) -> None:
        self._fallback_rows.append(row)
        with self._fallback_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def add(self, card: BaseEvidenceCard) -> str | None:
        """添加证据卡；若与已有卡去重键冲突则跳过并返回 None（不写文件）。"""
        row = card.to_flat_dict()
        dedup_key = self._dedup_key(row)
        if dedup_key in self._keys:
            return None
        row["_search_text"] = f"{card.key_finding} {card.method_brief} {' '.join(card.tags)}"
        if self._table is not None:
            try:
                self._table.add([row])
                self._keys.add(dedup_key)
                return card.card_id
            except Exception:
                pass
        self._fallback_append(row)
        self._keys.add(dedup_key)
        return card.card_id

    @staticmethod
    def _make_key(doi: str, pmid: str, title: str, finding: str) -> str:
        """统一去重键：标识符 + finding 哈希，保证同一论文的不同 finding 各自成卡。"""
        finding_hash = hashlib.md5(finding.encode()).hexdigest()[:12]
        if doi:
            return f"doi:{doi}|{finding_hash}"
        if pmid:
            return f"pmid:{pmid}|{finding_hash}"
        return hashlib.md5(f"{title}|{finding}".encode()).hexdigest()

    @classmethod
    def _dedup_key(cls, row: dict[str, Any]) -> str:
        doi = (row.get("paper_doi") or "").strip().lower()
        pmid = (row.get("paper_pmid") or "").strip()
        title = (row.get("paper_title") or "").strip().lower()
        finding = (row.get("key_finding") or "").strip()[:200]
        return cls._make_key(doi, pmid, title, finding)

    def dedup_keys(self) -> set[str]:
        """当前已存卡的去重键快照（供循环层判断新增卡）。"""
        return set(self._keys)

    def key_for_card(self, card: BaseEvidenceCard) -> str:
        src = getattr(card, "source_paper", None)
        doi = (getattr(src, "doi", None) or "").strip().lower() if src else ""
        pmid = (getattr(src, "pmid", None) or "").strip() if src else ""
        title = (getattr(src, "title", None) or "").strip().lower() if src else ""
        finding = (getattr(card, "key_finding", "") or "").strip()[:200]
        return self._make_key(doi, pmid, title, finding)

    def dedup_existing(self) -> int:
        seen: dict[str, dict[str, Any]] = {}
        removed = 0
        for row in self._fallback_rows:
            key = self._dedup_key(row)
            if key in seen:
                removed += 1
            else:
                seen[key] = row
        self._fallback_rows = list(seen.values())
        self._keys = set(seen.keys())
        if self._fallback_path.exists():
            self._fallback_path.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in self._fallback_rows) + "\n",
                encoding="utf-8",
            )
        return removed

    def add_many(self, cards: list[BaseEvidenceCard]) -> list[str | None]:
        ids: list[str | None] = []
        for c in cards:
            ids.append(self.add(c))
        return ids

    def query_scalar(
        self,
        filters: dict[str, Any],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self._table is not None:
            try:
                q = self._table.query()
                for k, v in filters.items():
                    if isinstance(v, list):
                        q = q.where(f"{k} IN {tuple(v)}" if len(v) > 1 else f"{k} = '{v[0]}'")
                    else:
                        q = q.where(f"{k} = '{v}'")
                return q.limit(limit).to_list()
            except Exception:
                pass
        return self._fallback_query_scalar(filters, limit)

    def _fallback_query_scalar(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for row in self._fallback_rows:
            match = True
            for k, v in filters.items():
                rv = row.get(k)
                if isinstance(v, list):
                    if rv not in v:
                        match = False
                        break
                elif rv != v:
                    match = False
                    break
            if match:
                results.append(row)
                if len(results) >= limit:
                    break
        return results

    def search_text(self, text: str, limit: int = 20) -> list[dict[str, Any]]:
        if self._table is not None:
            try:
                return (
                    self._table.search(text, query_type="fts").limit(limit).to_list()
                )
            except Exception:
                pass
        text_lower = text.lower()
        results: list[tuple[int, dict[str, Any]]] = []
        for row in self._fallback_rows:
            st = (row.get("_search_text") or "").lower()
            if text_lower in st:
                score = sum(1 for w in text_lower.split() if w in st)
                results.append((score, row))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in results[:limit]]

    def count(self) -> int:
        if self._table is not None:
            try:
                return self._table.count_rows()
            except Exception:
                pass
        return len(self._fallback_rows)

    def all_rows(self) -> list[dict[str, Any]]:
        if self._table is not None:
            try:
                return self._table.query().to_list()
            except Exception:
                pass
        return list(self._fallback_rows)

    def distinct_values(self, field: str) -> list[Any]:
        rows = self.all_rows()
        seen: list[Any] = []
        for r in rows:
            v = r.get(field)
            if v is not None and v not in seen:
                seen.append(v)
        return seen
