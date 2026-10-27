from fastapi import APIRouter
from fastapi.responses import JSONResponse

# Important: text parser service has its own internal singleton cache
from api.dependencies import get_text_parser_service

router = APIRouter()

@router.post("/chat", response_class=JSONResponse)
async def chat_endpoint(request: dict):
    service = get_text_parser_service()
    
    if service is None:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": {
                    "code": "SERVICE_NOT_READY",
                    "message": "Text parser service chưa sẵn sàng"
                }
            }
        )
    
    result = service.parse_query(request)
    
    # Text parser service returns ParseResult which has a dict data and http status
    # In the original code, `result.data` was returned directly. But actually in app.py:
    # return JSONResponse(status_code=result.http_status, content=result.data)
    
    if hasattr(result, 'http_status') and hasattr(result, 'data'):
        return JSONResponse(status_code=result.http_status, content=result.data)
    else:
        # Fallback if the parser changes its return signature
        return JSONResponse(status_code=200, content=result)
