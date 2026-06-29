# eval_rag.py — run from repo root: python eval_rag.py
import os, json
from qdrant_client.models import SparseVector
from ragas import EvaluationDataset, evaluate
from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI
from ragas.metrics import (LLMContextPrecisionWithReference, LLMContextRecall,
                           Faithfulness, ResponseRelevancy)          # ← add the last two
from ragas.embeddings import LangchainEmbeddingsWrapper              # ← new line
from main import (embeddings, sparse_model, qdrant, _rrf, _rerank_scores,
                  COLLECTION_NAME, FETCH_K, FINAL_K,
                  _build_system_prompt, call_llm, CHOSEN_MODEL,
                  _is_directions_query, _extract_origin_dest,
                  get_events_context, get_transit_context,
                  embeddings, sparse_model, qdrant, _rrf, _rerank_scores,
                  COLLECTION_NAME, FETCH_K, FINAL_K)     

# Reuse the REAL retrieval components — this evaluates your actual pipeline,
# not a reimplementation. Importing main loads the embedding/sparse/rerank
# models once (heavy but fine for a manual run); the scheduler does NOT start
# (that only happens under uvicorn's lifespan).
GOLDEN_PATH = "golden_set.jsonl"


def retrieve_chunks(question: str, k: int = FINAL_K) -> list[str]:
    """Mirror of retrieve_context, but returns the top-k chunk texts as a
    list (what RAGAS wants) instead of a joined string. Same dense+sparse →
    RRF → cross-encoder rerank, so it measures the real retrieval."""
    dense = embeddings.embed_query(question)
    se = list(sparse_model.query_embed(question))[0]
    sv = SparseVector(indices=se.indices.tolist(), values=se.values.tolist())

    dr = qdrant.query_points(collection_name=COLLECTION_NAME, query=dense, using="dense",  limit=20)
    sr = qdrant.query_points(collection_name=COLLECTION_NAME, query=sv,    using="sparse", limit=20)

    cands = _rrf(dr, sr)[:FETCH_K]
    if not cands:
        return []
    pairs  = [[question, h.payload["text"]] for h in cands]
    scores = _rerank_scores(pairs)
    ranked = sorted(zip(scores, cands), key=lambda x: x[0], reverse=True)[:k]
    return [h.payload["text"] for _, h in ranked]


def generate_answer(question: str, chunks: list[str]) -> str:
    context = "\n\n".join(f"Source [{i}] (kb): {c}" for i, c in enumerate(chunks))
    sys = _build_system_prompt(context, summary="", is_web=False)
    return call_llm([{"role": "system", "content": sys},
                     {"role": "user", "content": question}], CHOSEN_MODEL)

def build_dataset(golden: list[dict]) -> EvaluationDataset:
    rows = []
    for item in golden:
        chunks = retrieve_chunks(item["question"])          # retrieve once…
        rows.append({
            "user_input":         item["question"],
            "retrieved_contexts": chunks,
            "response":           generate_answer(item["question"], chunks),  # ← …reuse for generation
            "reference":          item["ground_truth"],
        })
    return EvaluationDataset.from_list(rows)


def main():
    with open(GOLDEN_PATH) as f:
        golden = [json.loads(l) for l in f if l.strip()]

    dataset = build_dataset(golden)

    # Judge LLM routed through OpenRouter. Use a capable-but-cheap model —
    # the metrics need real reasoning, so don't go too small.
    judge = ChatOpenAI(
        model="deepseek/deepseek-v3.2",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        temperature=0,
    )
    evaluator_llm = LangchainLLMWrapper(judge)

    result = evaluate(
        dataset=dataset,
        metrics=[LLMContextPrecisionWithReference(), LLMContextRecall(),
                 Faithfulness(), ResponseRelevancy()],                   
        llm=evaluator_llm,
        embeddings=LangchainEmbeddingsWrapper(embeddings),             
    )
    print(result)                       # e.g. {'llm_context_precision_with_reference': 0.78, 'context_recall': 0.71}
    result.to_pandas().to_csv("eval_results.csv", index=False)
    print("per-question scores → eval_results.csv")

def test_directions_routing():
    # the query lands on the directions path at all
    assert _is_directions_query("how do I get from the airport to Blloku")

def test_origin_dest_parse():
    # "to Y from X" word-order parses correctly (the bug we fixed)
    o, d = _extract_origin_dest("how do I get to the airport from Skanderbeg Square")
    assert "skanderbeg" in o.lower() and "airport" in d.lower()

def test_events_in_window():
    # events path returns rows for a time-sensitive query
    ctx, srcs = get_events_context("what's on this weekend")
    assert ctx == "" or "EVENTS" in ctx   # empty is valid (no events); junk is not

def test_transit_resolves():
    ctx, _ = get_transit_context("from Skanderbeg Square to Blloku")
    assert "By bus" in ctx or "Driving" in ctx   # at least one mode resolved

if __name__ == "__main__":
    main()