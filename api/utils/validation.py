import os
import re
import uuid
import contextlib
import tempfile
import io
import zipfile
from fastapi import HTTPException, UploadFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".txt", ".pdf", ".docx", ".doc"}
ALLOWED_MIME_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
LEGACY_OFFICE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


async def read_upload_file(file: UploadFile, max_size: int | None = None) -> bytearray:
    """Read an uploaded file in bounded chunks and reject oversized files early."""
    limit = MAX_FILE_SIZE if max_size is None else max_size
    content = bytearray()

    while True:
        remaining_with_probe = limit - len(content) + 1
        chunk = await file.read(min(1024 * 1024, remaining_with_probe))
        if not chunk:
            return content
        if len(content) + len(chunk) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File quá lớn. Giới hạn: {limit / (1024 * 1024):.1f}MB",
            )
        content.extend(chunk)


def _is_valid_xlsx(content: bytes | bytearray) -> bool:
    """Verify that ZIP-detected content is a readable Office Open XML workbook."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = set(archive.namelist())
        if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(members):
            return False

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        workbook.close()
        return True
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError):
        return False


@contextlib.contextmanager
def managed_temp_file(content: bytes, suffix: str):
    """Context manager to handle temporary file creation and cleanup automatically."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        yield tmp_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception as e:
                pass

def validate_file_upload(filename: str, content: bytes | bytearray) -> tuple[str, str]:
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File quá lớn. Giới hạn: {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng không hỗ trợ. Chỉ chấp nhận: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    if extension in {".xls", ".doc"} and not content.startswith(LEGACY_OFFICE_SIGNATURE):
        raise HTTPException(
            status_code=400,
            detail=f"File {extension} không đúng định dạng Office legacy hợp lệ."
        )
    
    try:
        import magic
        detected_mime = magic.from_buffer(content[:2048], mime=True)
        
        if extension == ".csv":
            if detected_mime in ("application/zip", "application/x-zip-compressed",
                               "application/octet-stream", "application/pdf"):
                raise HTTPException(
                    status_code=400,
                    detail="File không phải CSV hợp lệ (nội dung không đúng định dạng)"
                )
        elif extension in {".xlsx", ".xls"}:
            is_legacy_excel = (
                extension == ".xls"
                and detected_mime.lower() in {"application/cdfv2", "application/x-ole-storage"}
            )
            allowed_mime_prefixes = (
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats",
                "application/excel",
                "application/msexcel",
                "application/x-excel",
                "zz-win32/",
            )
            office_indicators = ("office", "document", "spreadsheet", "excel")
            is_allowed = (
                detected_mime.startswith(allowed_mime_prefixes) or
                any(ind in detected_mime.lower() for ind in office_indicators) or
                detected_mime == "application/octet-stream"
            )
            if detected_mime in ("application/zip", "application/x-zip-compressed"):
                is_allowed = extension == ".xlsx" and _is_valid_xlsx(content)
            is_allowed = is_allowed or is_legacy_excel
            if not is_allowed and detected_mime not in ("text/plain", "text/csv"):
                raise HTTPException(
                    status_code=400,
                    detail=f"File không phải Excel hợp lệ: {detected_mime}"
                )
        elif extension == ".pdf":
            if not detected_mime.startswith("application/pdf"):
                raise HTTPException(
                    status_code=400,
                    detail="File không phải PDF hợp lệ"
                )
        elif extension in {".docx", ".doc"}:
            is_legacy_word = (
                extension == ".doc"
                and detected_mime.lower() in {"application/cdfv2", "application/x-ole-storage"}
            )
            if not is_legacy_word and not any(
                ind in detected_mime.lower() for ind in ["word", "document", "msword"]
            ):
                raise HTTPException(
                    status_code=400,
                    detail="File không phải Word hợp lệ"
                )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: python-magic library is required for file validation."
        )
    
    safe_name = re.sub(r'[^\w\s.-]', '_', filename)
    safe_name = re.sub(r'\.\.+', '.', safe_name)
    safe_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    
    return safe_name, extension
