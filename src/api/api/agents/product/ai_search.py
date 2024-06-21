from typing import List
import os
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential

def retrieve_documentation(
    request: str,
    index_name: str,
    embedding: List[float],
) -> List[dict]:
    
    search_client = SearchClient(
            endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
            index_name=index_name,
            credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API")),
        )

    vector_query = VectorizedQuery(
        vector=embedding, k_nearest_neighbors=3, fields="contentVector"
    )

    results = search_client.search(
        search_text="",  # Leave search_text empty since we're only using vector search
        vector_queries=[vector_query],
        top=3,
    )
    # results_list= list(results)
    #    # Place the breakpoint here

    docs = [
        {
            "id": doc["id"],
            "title": doc["title"],
            "content": doc["content"],
            "url": doc["url"],
        }
        for doc in results
    ]

    return docs