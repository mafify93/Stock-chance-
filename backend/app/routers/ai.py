from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import ai_analyst, models
from ..ai_combine import combine
from ..ml.model import ml_predictor
from ..providers import yahoo
from ..signals import analyze

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/analysis/{symbol}", response_model=models.AIAnalysisResponse)
async def ai_analysis(symbol: str):
    """AI-generated take on a symbol, combining:

    - the rule-based technical signal (`/api/signal`)
    - a machine-learning model's probability the price is higher in N days
      (if a trained model is available)
    - an LLM analyst's plain-English summary (if `ANTHROPIC_API_KEY` is set)

    into one `combined_action` / `combined_confidence`.
    """
    symbol = symbol.upper()
    try:
        df = await run_in_threadpool(yahoo.get_history, symbol, "1y", "1d")
        signal_result = await run_in_threadpool(analyze, symbol, df)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Signal computation failed: {exc}") from exc

    ml_result = await run_in_threadpool(ml_predictor.predict, df)

    signal_dict = {
        "action": signal_result.action,
        "score": signal_result.score,
        "confidence": signal_result.confidence,
        "price": signal_result.price,
        "reasons": signal_result.reasons,
    }

    llm_result = None
    if ai_analyst.configured():
        llm_result = await run_in_threadpool(ai_analyst.analyze, symbol, signal_dict, ml_result)

    combined_action, combined_confidence = combine(signal_dict, ml_result, llm_result)

    return models.AIAnalysisResponse(
        symbol=symbol,
        price=signal_result.price,
        signal=models.SignalSummary(**signal_dict),
        ml=models.MLPrediction(**ml_result) if ml_result else None,
        llm=models.LLMAnalysis(**llm_result) if llm_result else None,
        llm_configured=ai_analyst.configured(),
        combined_action=combined_action,
        combined_confidence=combined_confidence,
    )
