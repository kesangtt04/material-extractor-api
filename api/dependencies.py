import io
import threading
import logging
import time
from contextlib import redirect_stdout, redirect_stderr

logger = logging.getLogger(__name__)

_model_cache = {"model": None, "loaded": False}
_model_lock = threading.Lock()

_text_parser_cache = {
    "service": None,
    "loaded": False,
    "failed": False,
    "retry_after": 0,
    "backoff_seconds": 30,  # initialized upfront; doubles on each failure, capped at 300s
}
_text_parser_lock = threading.Lock()


def get_warmed_model():
    """Get cached model or load it if not warmed up yet."""
    if not _model_cache["loaded"]:
        with _model_lock:
            if not _model_cache["loaded"]:
                from file_pipeline.extractor import get_ml_model
                _model_cache["model"] = get_ml_model()
                _model_cache["loaded"] = True
                if _model_cache["model"]:
                    logger.info("ML model warmed up successfully")
                else:
                    logger.warning("ML model warmup failed - model files may be missing")
    return _model_cache["model"]


def get_text_parser_service():
    """Get cached text parser service or load it if not warmed up yet.

    Implements exponential backoff to avoid retry storm on permanent failures.
    Startup output from PyTorch/other libraries is captured and forwarded to
    the logger (DEBUG on success, WARNING on failure) instead of being silently
    discarded or printed directly to the console.
    """
    if not _text_parser_cache["loaded"]:
        with _text_parser_lock:
            if not _text_parser_cache["loaded"]:
                if _text_parser_cache["failed"] and time.time() < _text_parser_cache["retry_after"]:
                    logger.warning("Text parser service in backoff period, skipping retry")
                    return None

                captured_out = io.StringIO()
                captured_err = io.StringIO()
                try:
                    with redirect_stdout(captured_out), redirect_stderr(captured_err):
                        from text_pipeline.service import TextParserService
                        _text_parser_cache["service"] = TextParserService()
                        _text_parser_cache["loaded"] = True
                        _text_parser_cache["failed"] = False
                        _text_parser_cache["retry_after"] = 0
                        _text_parser_cache["backoff_seconds"] = 30

                    # Forward captured startup output so it remains visible in log files
                    out = captured_out.getvalue()
                    err = captured_err.getvalue()
                    if out:
                        logger.debug("[TextParserService stdout]\n%s", out.rstrip())
                    if err:
                        logger.debug("[TextParserService stderr]\n%s", err.rstrip())

                    logger.info("Text parser service loaded successfully")

                except Exception as e:
                    # Emit captured output at WARNING so startup errors are never lost
                    out = captured_out.getvalue()
                    err = captured_err.getvalue()
                    if out:
                        logger.warning("[TextParserService stdout during failure]\n%s", out.rstrip())
                    if err:
                        logger.warning("[TextParserService stderr during failure]\n%s", err.rstrip())

                    logger.error("Text parser service warmup failed: %s", e, exc_info=True)
                    _text_parser_cache["service"] = None
                    _text_parser_cache["loaded"] = False
                    _text_parser_cache["failed"] = True
                    current_backoff = _text_parser_cache["backoff_seconds"]
                    _text_parser_cache["backoff_seconds"] = min(current_backoff * 2, 300)
                    _text_parser_cache["retry_after"] = time.time() + current_backoff
                    logger.info("Next retry in %ss", current_backoff)

    return _text_parser_cache["service"]


def get_health_status():
    model = _model_cache["model"]
    text_service = _text_parser_cache["service"]
    file_pipeline_ready = _model_cache["loaded"] and model is not None
    chat_pipeline_ready = (
        _text_parser_cache["loaded"]
        and text_service is not None
        and text_service.is_ready()
    )
    return {
        "status": "healthy" if file_pipeline_ready and chat_pipeline_ready else "degraded",
        "file_pipeline": {
            "model_loaded": file_pipeline_ready,
            "model_version": getattr(model, "_tier2_version", None) if model else None
        },
        "chat_pipeline": {
            "service_loaded": _text_parser_cache["loaded"] and text_service is not None,
            "parser_ready": chat_pipeline_ready
        }
    }
