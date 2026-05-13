import os
import requests
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# --- CONFIGURATION ---
load_dotenv()

WIKI_URL = os.getenv("WIKI_URL")
WIKI_TOKEN = os.getenv("WIKI_TOKEN")
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

# 1. Fetch all relevant wiki pages
def get_all_wiki_data():
    headers = {"Authorization": f"Bearer {WIKI_TOKEN}"}
    list_query = "{ pages { list { id title path } } }"
    res = requests.post(WIKI_URL, json={'query': list_query}, headers=headers).json()

    documents = []
    for p in res['data']['pages']['list']:
        if "banka" in p['path'] or "sektori" in p['path']:
            content_query = "query($id:Int!){pages{single(id:$id){content}}}"
            c_res = requests.post(
                WIKI_URL,
                json={'query': content_query, 'variables': {'id': p['id']}},
                headers=headers
            ).json()
            documents.append({
                "text": c_res['data']['pages']['single']['content'],
                "metadata": {"title": p['title'], "path": p['path']}
            })
    return documents

# 2. RAG PIPELINE
print("Duke shkarkuar të dhënat nga Wiki...")
raw_docs = get_all_wiki_data()

text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)

texts = []
metadatas = []

for doc in raw_docs:
    chunks = text_splitter.split_text(doc['text'])
    texts.extend(chunks)
    metadatas.extend([doc['metadata']] * len(chunks))

print(f"Teksti u nda në {len(texts)} chunks.")

# 3. Embeddings & Vector Store
print("Duke krijuar Vector Database (kjo mund të zgjasë pak herën e parë)...")
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

vector_db = Chroma.from_texts(
    texts=texts,
    embedding=embeddings,
    metadatas=metadatas,
    persist_directory=CHROMA_DIR
)

print(f" Database u krijua me sukses në folderin {CHROMA_DIR}!")

# 4. Quick search test
query = "Sa është mjaftueshmëria e kapitalit për Intesa Sanpaolo?"
results = vector_db.similarity_search(query, k=2)

print("\nTest kërkimi:")
for res in results:
    print(f"Burimi: {res.metadata['title']}")
    print(f"Teksti: {res.page_content[:200]}...")