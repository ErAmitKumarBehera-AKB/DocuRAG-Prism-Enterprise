from backend.app.deps import get_answerer, get_reranker, get_retriever, get_trust_layer, get_current_user
from backend.app.logging_utils import stage_timer
from backend.core.schemas import AskRequest, AskResponse, CompareResponse, LatencyBreakdown, BatchDecisionRequest, BatchDecisionResponse
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/query", tags=["query"])

@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    retriever = Depends(get_retriever),
    reranker = Depends(get_reranker),
    answerer = Depends(get_answerer),
    trust = Depends(get_trust_layer),
    user: dict = Depends(get_current_user)
):
    target_k = max(req.k, 10) if not req.file_ids else req.k
    with stage_timer() as retrieve_ms:
        candidates = retriever.retrieve(req.question, target_k * 4, req.file_ids)
        
    with stage_timer() as rerank_ms:
        reranked = reranker.rerank(req.question, candidates)
        if hasattr(reranker, "select_balanced_evidence"):
            evidence = reranker.select_balanced_evidence(reranked, target_k)
        else:
            evidence = reranked[:target_k]
        
    with stage_timer() as generate_ms:
        ans_text, citations = answerer.answer(req.question, evidence)
        
    with stage_timer() as verify_ms:
        confidence, refused = trust.evaluate(req.question, ans_text, citations, evidence)
        
    total_ms = retrieve_ms["ms"] + rerank_ms["ms"] + generate_ms["ms"] + verify_ms["ms"]
    
    latency = LatencyBreakdown(
        retrieve_ms=retrieve_ms["ms"],
        rerank_ms=rerank_ms["ms"],
        generate_ms=generate_ms["ms"],
        verify_ms=verify_ms["ms"],
        total_ms=total_ms
    )
    
    return AskResponse(
        answer=ans_text,
        citations=citations,
        confidence=confidence,
        refused=refused,
        refusal_message=None if not refused else ans_text,
        latency=latency,
        highlighted_page_url=None
    )

@router.post("/compare", response_model=CompareResponse)
def compare(req: AskRequest, retriever = Depends(get_retriever), user: dict = Depends(get_current_user)):
    keyword_results = retriever.retrieve_sparse(req.question, req.k)
    semantic_results = retriever.retrieve_dense(req.question, req.k)
    return CompareResponse(
        keyword_results=keyword_results,
        semantic_results=semantic_results
    )

@router.post("/batch-decisions", response_model=BatchDecisionResponse)
def batch_decisions(
    req: BatchDecisionRequest,
    retriever = Depends(get_retriever),
    reranker = Depends(get_reranker),
    answerer = Depends(get_answerer),
    trust = Depends(get_trust_layer),
    user: dict = Depends(get_current_user)
):
    results = {}
    for q in req.questions:
        results[q] = {}
        for fid in req.file_ids:
            with stage_timer() as retrieve_ms:
                candidates = retriever.retrieve(q, 5 * 4, [fid])
            with stage_timer() as rerank_ms:
                evidence = reranker.rerank(q, candidates)[:5]
            with stage_timer() as generate_ms:
                ans_text, citations = answerer.answer(q, evidence)
            with stage_timer() as verify_ms:
                confidence, refused = trust.evaluate(q, ans_text, citations, evidence)
                
            total_ms = retrieve_ms["ms"] + rerank_ms["ms"] + generate_ms["ms"] + verify_ms["ms"]
            latency = LatencyBreakdown(
                retrieve_ms=retrieve_ms["ms"],
                rerank_ms=rerank_ms["ms"],
                generate_ms=generate_ms["ms"],
                verify_ms=verify_ms["ms"],
                total_ms=total_ms
            )
            
            results[q][fid] = AskResponse(
                answer=ans_text,
                citations=citations,
                confidence=confidence,
                refused=refused,
                refusal_message=None if not refused else ans_text,
                latency=latency
            )
            
    return BatchDecisionResponse(results=results)
