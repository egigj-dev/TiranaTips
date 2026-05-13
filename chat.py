import os
import requests
import json
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# --- 1. CONFIGURATION ---
load_dotenv()

CHOSEN_MODEL = os.getenv("CHOSEN_MODEL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

# --- 2. LOAD VECTOR DB ---
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
vector_db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)

def ask_ai(question):
    # Retrieval
    docs = vector_db.similarity_search(question, k=3)
    context = "\n\n".join([f"Burimi [{i}]: {d.page_content}" for i, d in enumerate(docs)])

    # Prompt Engineering
    prompt = f"""Ti je një ekspert i sektorit bankar në Shqipëri. 
Përgjigju vetëm duke u bazuar në kontekstin e mëposhtëm.

KONTEKSTI:
{context}

PYETJA: {question}
PËRGJIGJJA:"""

    # API Call
    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps({
            "model": CHOSEN_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        })
    )

    res_json = response.json()
    if "choices" in res_json:
        return res_json['choices'][0]['message']['content']
    else:
        return f"Error: {res_json}"

if __name__ == "__main__":
    print(f" Duke përdorur modelin: {CHOSEN_MODEL}")
    while True:
        q = input("\nPyetja juaj: ")
        if q.lower() == 'exit':
            break
        print("Thinking...")
        print(f"\nAI: {ask_ai(q)}")