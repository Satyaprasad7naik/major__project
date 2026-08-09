import asyncio
from typing import Dict, Any
from app.modules.preprocessing.components.table_retriever import TableRetriever
from app.modules.preprocessing.components.column_retriever import ColumnRetriever
from app.modules.preprocessing.components.few_shot_retriever import FewShotRetriever
from app.modules.preprocessing.components.entity_extractor import EntityExtractor

class PreprocessingService:
    """
    Orchestrates parallel execution of preprocessing sub-tasks.
    """
    def __init__(self):
        self.table_retriever = TableRetriever()
        self.column_retriever = ColumnRetriever()
        self.few_shot_retriever = FewShotRetriever()
        self.entity_extractor = EntityExtractor()

    async def process(self, query: str, domain: str = "general") -> Dict[str, Any]:
        """
        Runs table retrieval first (local/0ms), then processes columns, few-shots,
        and entity extraction (passing the relevant tables) concurrently.
        """
        # 1. Retrieve tables first (0ms local keyword check)
        tables = await self.table_retriever.retrieve(query)
        
        # 2. Run the remaining retrievers and extractors concurrently
        t2 = self.column_retriever.retrieve(query)
        t3 = self.few_shot_retriever.retrieve(query, domain=domain)
        t4 = self.entity_extractor.extract(query, domain=domain, relevant_tables=tables)

        columns, few_shots, entities = await asyncio.gather(t2, t3, t4)

        return {
            "relevant_tables": tables,
            "relevant_columns": columns,
            "few_shot_examples": few_shots,
            "entities": entities,
            "domain": domain
        }

# Singleton instance
preprocessing_service = PreprocessingService()
