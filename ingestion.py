"""
ingestion.py — Merr faqet nga Wiki.js, i ndan në chunks,
               i kthen në vektorë DENSE + SPARSE dhe i ruan në Qdrant lokal.

Ndryshim nga versioni i mëparshëm:
  - Koleksioni tani ruan dy vektorë për çdo chunk:
      "dense"  → embedding semantik (si më parë)
      "sparse" → BM25 keyword vector (i ri)
  - Kjo lejon kërkim hibrid (dense + BM25) me RRF fusion

Ekzekuto: python ingestion.py
  KUJDES: Ky skript fshin dhe rindërton koleksionin. Të gjitha të dhënat
          e vjetra do të zëvendësohen. Kjo është e nevojshme sepse
          skema e Qdrant-it nuk mund të ndryshohet pas krijimit.

Instalo varësitë e reja:
  pip install fastembed
"""
import os
import uuid
import requests
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    PointStruct,
    SparseVector,
)
from langchain_huggingface import HuggingFaceEmbeddings
from fastembed import SparseTextEmbedding

load_dotenv()

WIKI_URL        = os.getenv("WIKI_URL")
WIKI_TOKEN      = os.getenv("WIKI_TOKEN")
QDRANT_URL      = os.getenv("QDRANT_URL", "http://qdrant:6333")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
COLLECTION_NAME = "wiki_banking"

# --- HAPI 1: Lidhja me Qdrant server (HTTP) ---
client = QdrantClient(url=QDRANT_URL)


def recreate_collection(vector_size: int):
    """
    Fshin koleksionin ekzistues (nëse ka) dhe krijon një të ri me skemë hibride.

    Pse fshijmë dhe rikrijojmë?
    Qdrant nuk lejon shtimin e sparse vectors në një koleksion ekzistues me
    vetëm dense vectors. Skema është e pandryshueshme pas krijimit — kjo është
    një kufizim i arkitekturës së Qdrant-it, jo i kodit tonë.

    Skema e re:
      vectors_config["dense"]  — vektori semantik 384-dimensional, distanca COSINE
      sparse_vectors_config["sparse"] — vektori BM25, i indeksuar me inverted index
    """
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME in existing:
        print(f"Duke fshirë koleksionin e vjetër '{COLLECTION_NAME}'...")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        # Dense vectors: named "dense", 384-dim, cosine similarity
        vectors_config={
            "dense": VectorParams(size=vector_size, distance=Distance.COSINE)
        },
        # Sparse vectors: named "sparse", built-in inverted index for BM25
        # on_disk=False keeps the index in RAM for fast queries
        sparse_vectors_config={
            "sparse": SparseVectorParams(
                index=SparseIndexParams(on_disk=False)
            )
        },
    )
    print(f"Koleksioni hibrid '{COLLECTION_NAME}' u krijua me sukses.")


# --- HAPI 2: Merr faqet nga Wiki.js ---
def fetch_wiki_pages() -> list[dict]:
    headers = {"Authorization": f"Bearer {WIKI_TOKEN}"}
    list_q  = "{ pages { list { id title path } } }"
    pages   = requests.post(WIKI_URL, json={"query": list_q}, headers=headers).json()

    documents = []
    for p in pages["data"]["pages"]["list"]:
        #if any(kw in p["path"] for kw in ("tirana",)):
        if True:  # Merr të gjitha faqet, pa filtrim
            content_q = "query($id:Int!){pages{single(id:$id){content}}}"
            content   = requests.post(
                WIKI_URL,
                json={"query": content_q, "variables": {"id": p["id"]}},
                headers=headers
            ).json()["data"]["pages"]["single"]["content"]

            documents.append({
                "text": content,
                "metadata": {"title": p["title"], "path": p["path"]}
            })
    print(f"U gjetën {len(documents)} faqe relevante.")
    return documents


# --- HAPI 3: Chunking ---
def chunk_documents(documents: list[dict]) -> tuple[list[str], list[dict]]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    texts, metas = [], []
    for doc in documents:
        chunks = splitter.split_text(doc["text"])
        texts.extend(chunks)
        metas.extend([doc["metadata"]] * len(chunks))
    print(f"Teksti u nda në {len(texts)} chunks.")
    return texts, metas


# --- HAPI 4: Embed + Ruaj në Qdrant ---
def embed_and_store(texts: list[str], metas: list[dict]):
    # ── Dense embeddings (semantic) ──
    print("Duke krijuar dense embeddings (semantike)...")
    dense_model   = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    dense_vectors = dense_model.embed_documents(texts)  # list[list[float]]

    # ── Sparse embeddings (BM25 keyword) ──
    # SparseTextEmbedding("Qdrant/bm25") shkarkon modelin BM25 të Qdrant-it herën
    # e parë (~15MB). Ky model tokenon tekstin dhe llogarit peshën BM25 të çdo fjale.
    #
    # Çfarë kthen: çdo embedding ka dy lista:
    #   .indices → ID-të e fjalëve (integer për çdo fjalë unike në chunk)
    #   .values  → pesha BM25 e çdo fjale (float, sa e rëndësishme është fjala)
    #
    # Shembull: chunk "NPL ratio është 5%" mund të kthejë:
    #   indices=[42, 891, 1203, 77]  (ID-të e "npl", "ratio", "është", "5")
    #   values= [2.1, 1.4, 0.3, 0.9] (BM25 nënvizon "npl" dhe "ratio")
    print("Duke shkarkuar BM25 modelin dhe duke krijuar sparse embeddings...")
    sparse_model      = SparseTextEmbedding(model_name="Qdrant/bm25")
    sparse_embeddings = list(sparse_model.embed(texts))
    # ↑ embed() (jo query_embed()) përdoret për dokumente — peshon termat
    #   ndryshe nga pyetjet (document-side BM25)

    # ── Ndërtimi i koleksionit ──
    recreate_collection(vector_size=len(dense_vectors[0]))

    # ── Ndërtimi i pikave dhe ngarkimi në Qdrant ──
    points = []
    for dense_vec, sparse_emb, txt, meta in zip(
        dense_vectors, sparse_embeddings, texts, metas
    ):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    # Dense vector: lista e zakonshme e float-eve
                    "dense": dense_vec,
                    # Sparse vector: vetëm termat jo-zero (efiçient)
                    "sparse": SparseVector(
                        indices=sparse_emb.indices.tolist(),
                        values=sparse_emb.values.tolist(),
                    ),
                },
                payload={"text": txt, **meta},
            )
        )

    # Ngarko në batch (100 njësi në çdo kërkesë)
    batch_size = 100
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i : i + batch_size])
        print(f"  Ngarkuar {min(i + batch_size, len(points))}/{len(points)} pika...")

    print(f"✓ {len(points)} pika (dense + sparse) u ruajtën në Qdrant server.")


# --- MAIN ---
if __name__ == "__main__":
    docs         = fetch_wiki_pages()
    texts, metas = chunk_documents(docs)
    embed_and_store(texts, metas)
    client.close()
    print("\nIngestion hibrid përfundoi me sukses!")
    print("Tani rinis serverin: uvicorn main:app --reload")
