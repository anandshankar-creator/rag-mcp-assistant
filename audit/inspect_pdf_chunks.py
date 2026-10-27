import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.vectorstore import get_vector_store

store = get_vector_store()
res = store.collection.get(where={'source_file': 'Guardian_AI_Project_Phase_1_Report 2.0.pdf'}, include=['documents', 'metadatas'])
print(f"Total chunks for Guardian AI: {len(res['ids'])}")
for i, (d, m) in enumerate(zip(res['documents'], res['metadatas'])):
    p = m.get('page')
    print(f"--- Chunk {i+1} (Page {p}) ---")
    print(d[:250].strip())
    print()
