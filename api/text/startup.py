"""Fail-fast validation for parser artifacts and loaded dependencies."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional

REQUIRED_TAGS = {"B-NAME", "B-QTY", "B-UNIT", "B-CODE"}


class StartupValidationError(RuntimeError):
    """Raised when the selected parser stack is not safe to serve."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _require_file(path: str, label: str) -> None:
    if not path or not os.path.isfile(path):
        raise StartupValidationError("MISSING_ARTIFACT", f"{label} not found: {path}")


def _validate_vocab(vocab: Any) -> None:
    for mapping_name in ("word2idx", "char2idx", "label2idx"):
        mapping = getattr(vocab, mapping_name, None)
        if not isinstance(mapping, dict):
            raise StartupValidationError("INVALID_VOCAB", f"Missing vocabulary mapping: {mapping_name}")
    for mapping_name in ("word2idx", "char2idx"):
        mapping = getattr(vocab, mapping_name)
        if "<PAD>" not in mapping or "<UNK>" not in mapping:
            raise StartupValidationError("INVALID_VOCAB", f"{mapping_name} must contain <PAD> and <UNK>")
    missing_tags = REQUIRED_TAGS.difference(getattr(vocab, "label2idx", {}))
    if missing_tags:
        raise StartupValidationError("INVALID_VOCAB", f"Missing required tags: {sorted(missing_tags)}")


def _validate_checkpoint(checkpoint: Any) -> None:
    if not isinstance(checkpoint, dict) or "model_state_dict" not in checkpoint:
        raise StartupValidationError("INVALID_CHECKPOINT", "BiLSTM checkpoint must contain model_state_dict")


def validate_artifacts(
    mode: str,
    *,
    crf_model_path: Optional[str] = None,
    bilstm_model_path: Optional[str] = None,
    vocab_path: Optional[str] = None,
    loaded_vocab: Any = None,
    loaded_vocab_source: Optional[str] = None,
    products_path: Optional[str] = None,
    crf_loader: Optional[Callable[[str], Any]] = None,
    bilstm_loader: Optional[Callable[[str, Optional[str]], Any]] = None,
    vocab_loader: Optional[Callable[[str], Any]] = None,
    checkpoint_loader: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Validate only artifacts required by ``mode`` and return a report."""
    if mode not in {"crf", "bilstm", "hybrid"}:
        raise StartupValidationError("INVALID_MODE", f"Unsupported parser mode: {mode}")

    report: Dict[str, Any] = {"mode": mode, "crf": None, "bilstm": None, "products": None}
    if mode in {"crf", "hybrid"}:
        _require_file(crf_model_path, "CRF model")
        try:
            loaded = crf_loader(crf_model_path) if crf_loader else True
            if loaded is None:
                raise ValueError("loader returned None")
        except StartupValidationError:
            raise
        except Exception as exc:
            raise StartupValidationError("MODEL_LOAD_ERROR", f"CRF model could not be loaded: {exc}") from exc
        report["crf"] = {"path": crf_model_path, "loaded": True}

    if mode in {"bilstm", "hybrid"}:
        _require_file(bilstm_model_path, "BiLSTM model")
        try:
            checkpoint = checkpoint_loader(bilstm_model_path) if checkpoint_loader else None
            if checkpoint is not None:
                _validate_checkpoint(checkpoint)

            vocab = loaded_vocab
            vocab_source = loaded_vocab_source or (
                "loaded" if loaded_vocab is not None else "embedded"
            )
            if vocab is None and vocab_path and os.path.isfile(vocab_path):
                if vocab_loader:
                    vocab = vocab_loader(vocab_path)
                vocab_source = "file"
            elif vocab is None and isinstance(checkpoint, dict):
                vocab = checkpoint.get("vocab")
                if vocab is not None:
                    vocab_source = "embedded"

            if vocab is None:
                _require_file(vocab_path, "BiLSTM vocabulary")
            else:
                _validate_vocab(vocab)
                report["vocab_size"] = len(getattr(vocab, "word2idx", {}))
            if bilstm_loader:
                loaded = bilstm_loader(bilstm_model_path, vocab_path)
                if loaded is None:
                    raise ValueError("loader returned None")
        except StartupValidationError:
            raise
        except Exception as exc:
            raise StartupValidationError("MODEL_LOAD_ERROR", f"BiLSTM artifacts could not be loaded: {exc}") from exc
        report["bilstm"] = {
            "model_path": bilstm_model_path,
            "vocab_path": vocab_path,
            "vocab_source": vocab_source,
            "loaded": True,
        }

    if products_path:
        _require_file(products_path, "Products database")
        try:
            with open(products_path, "r", encoding="utf-8") as handle:
                products = json.load(handle)
            if not isinstance(products, (dict, list)):
                raise ValueError("catalog root must be an object or array")
        except StartupValidationError:
            raise
        except Exception as exc:
            raise StartupValidationError("INVALID_CATALOG", f"Products database could not be loaded: {exc}") from exc
        report["products"] = {"path": products_path, "count": len(products), "loaded": True}

    report["status"] = "READY"
    return report
