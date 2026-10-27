import os
import re
import uuid
import time
import json
import logging
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from file_pipeline.extractor import extract_material_data_detailed, detect_tier_timing, stream_rows
from file_pipeline.extraction import extract_using_mapping
from api.utils.validation import read_upload_file, validate_file_upload, managed_temp_file

logger = logging.getLogger(__name__)

router = APIRouter()

TIER_LABELS = {
    "tier1": "Tầng 1 (Header mapping)",
    "tier1b": "Tầng 1b (SKU dictionary)",
    "tier2": "Tầng 2 (ML classification)",
    "none": "Không tầng nào xử lý được",
}

def _normalize_row(item):
    return {
        "ma_san_pham": item.get("ma_san_pham"),
        "ten_san_pham": item.get("ten_san_pham"),
        "don_vi": item.get("don_vi"),
        "so_luong": item.get("so_luong"),
    }

@router.post("/upload", response_class=JSONResponse)
async def upload(file: UploadFile = File(...)):
    try:
        content = await read_upload_file(file)
        safe_filename, suffix = validate_file_upload(file.filename, content)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail}
        )
    try:
        with managed_temp_file(content, suffix) as tmp_path:
            start = time.perf_counter()
            rows, metadata = extract_material_data_detailed(tmp_path)
            _ = (time.perf_counter() - start)
        
            normalized = [
                {
                    "Tên sản phẩm": item.get("ten_san_pham"),
                    "Mã sản phẩm": item.get("ma_san_pham"),
                    "Số lượng": item.get("so_luong"),
                    "Đơn vị": item.get("don_vi"),
                }
                for item in rows
            ]
        
            return normalized
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)}
        )

@router.post("/json", response_class=JSONResponse)
async def upload_json(file: UploadFile = File(...)):
    logger.info(f"[JSON API] Received file: {file.filename}")
    try:
        content = await read_upload_file(file)
        logger.info(f"[JSON API] File size: {len(content)} bytes")
        safe_filename, suffix = validate_file_upload(file.filename, content)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"file": file.filename, "error": exc.detail}
        )
    try:
        with managed_temp_file(content, suffix) as tmp_path:
            logger.info(f"[JSON API] Temp file: {tmp_path}")
            logger.info(f"[JSON API] Temp file size: {os.path.getsize(tmp_path)} bytes")

            rows, metadata = extract_material_data_detailed(tmp_path)
            logger.info(f"[JSON API] Pipeline result: tier={metadata.get('tier')}, rows={len(rows)}")
            normalized_rows = [_normalize_row(item) for item in rows]
            return {
                "file": file.filename,
                "tier": metadata.get("tier", "none"),
                "row_count": len(normalized_rows),
                "rows": normalized_rows,
            }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"file": file.filename, "error": str(exc)},
        )

@router.post("/detect", response_class=JSONResponse)
async def detect_only(file: UploadFile = File(...)):
    try:
        content = await read_upload_file(file)
        safe_filename, suffix = validate_file_upload(file.filename, content)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    try:
        with managed_temp_file(content, suffix) as tmp_path:
            detection_ms, candidate, tier, metadata = detect_tier_timing(tmp_path)
            return {
                "file": file.filename,
                "tier": tier,
                "tier_label": TIER_LABELS.get(tier, tier),
                "detection_ms": round(detection_ms, 1),
                "has_result": candidate is not None,
            }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

@router.post("/upload-stream")
async def upload_stream(file: UploadFile = File(...)):
    try:
        content = await read_upload_file(file)
        safe_filename, suffix = validate_file_upload(file.filename, content)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"file": file.filename, "error": exc.detail}
        )
    try:
        with managed_temp_file(content, suffix) as tmp_path:
            detection_ms, candidate, tier, metadata = detect_tier_timing(tmp_path)

            def event_stream():
                tier_label = TIER_LABELS.get(tier, tier)
                info = {
                    "tier": tier,
                    "tier_label": tier_label,
                    "detection_ms": round(detection_ms, 1),
                }
                if candidate is not None:
                    total = len(extract_using_mapping(
                        candidate[0], candidate[1],
                        candidate[2], candidate[3]
                    ))
                    info["total_rows"] = total
                    yield f"event: info\ndata: {json.dumps(info, ensure_ascii=False)}\n\n"
                    for chunk_rows, is_first, _, offset in stream_rows(
                        candidate[0], candidate[1], candidate[2], candidate[3]
                    ):
                        payload = {
                            'rows': [_normalize_row(r) for r in chunk_rows],
                            'offset': offset - len(chunk_rows),
                            'count': len(chunk_rows),
                            'is_first': is_first,
                        }
                        yield "event: rows\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                    yield "event: done\ndata: {}\n\n"
                else:
                    info["total_rows"] = 0
                    yield f"event: info\ndata: {json.dumps(info, ensure_ascii=False)}\n\n"
                    yield "event: done\ndata: {}\n\n"

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
    except Exception as exc:
        def error_stream():
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

@router.post("/benchmark")
async def benchmark_streaming_vs_batch(file: UploadFile = File(...)):
    import time
    try:
        content = await read_upload_file(file)
        safe_filename, suffix = validate_file_upload(file.filename, content)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    try:
        with managed_temp_file(content, suffix) as tmp_path:
            stream_start = time.perf_counter()
            detection_ms, candidate, tier, metadata = detect_tier_timing(tmp_path)
        
            if candidate is None:
                return {"error": "No valid mapping found", "tier": tier}
        
            first_chunk_ms = None
            chunks_count = 0
            total_rows = 0
        
            for chunk_rows, is_first, is_last, offset in stream_rows(
                candidate[0], candidate[1], candidate[2], candidate[3]
            ):
                chunks_count += 1
                total_rows = offset
                if is_first:
                    first_chunk_ms = (time.perf_counter() - stream_start) * 1000
        
            streaming_total_ms = (time.perf_counter() - stream_start) * 1000

            batch_start = time.perf_counter()
            detect_tier_timing(tmp_path) 
            extract_start = time.perf_counter()
        
            all_rows = extract_using_mapping(
                candidate[0], candidate[1], candidate[2], candidate[3]
            )
            extract_all_ms = (time.perf_counter() - extract_start) * 1000
            batch_total_ms = (time.perf_counter() - batch_start) * 1000
        
            json_str = json.dumps([_normalize_row(r) for r in all_rows], ensure_ascii=False)
            json_size_kb = len(json_str.encode('utf-8')) / 1024

            return {
                "file": file.filename,
                "total_rows": total_rows,
                "tier": tier,
                "streaming": {
                    "detection_ms": round(detection_ms, 1),
                    "first_chunk_ms": round(first_chunk_ms, 1) if first_chunk_ms else 0,
                    "total_ms": round(streaming_total_ms, 1),
                    "chunks": chunks_count,
                },
                "batch": {
                    "detection_ms": round(detection_ms, 1),
                    "extract_all_ms": round(extract_all_ms, 1),
                    "total_ms": round(batch_total_ms, 1),
                    "json_size_kb": round(json_size_kb, 1),
                }
            }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
