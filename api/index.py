import os
import json
import ssl
import urllib.request
import urllib.parse
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://znewxywawcpibiodmtnj.supabase.co").strip().rstrip("/").replace("/rest/v1", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_s2MTJ7z1DhS-PlWz1zwvGw_lKh7bb1P").strip()

MAX_TOTAL_SCORE = 320.0

app = FastAPI(title="Thanaweya Amma 2026 API")

# إتاحة CORS بشكل كامل
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# معالج أخطاء لمنع انقطاع CORS عند أي خطأ في السيرفر
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"خطأ خادم: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def fetch_from_supabase(endpoint_path: str):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint_path}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(f"Supabase HTTP {e.code}: {error_body}")
    except Exception as e:
        raise Exception(f"Connection Error: {str(e)}")

class StudentResult(BaseModel):
    seating_no: int
    name: str
    total_score: float
    percentage: float
    status: str
    school: Optional[str] = None
    governorate: Optional[str] = None

class SearchNameResult(BaseModel):
    seating_no: int
    name: str
    total_score: float
    status: str

# دعم المسارين معاً لمنع خطأ 404 في Vercel
@app.get("/api/result/{seating_no}", response_model=StudentResult)
@app.get("/result/{seating_no}", response_model=StudentResult)
def get_result(seating_no: str):
    seating_no = seating_no.strip()
    if not seating_no.isdigit():
        raise HTTPException(status_code=400, detail="رقم الجلوس يجب أن يتكون من أرقام فقط")

    path = f"results?seating_no=eq.{seating_no}&select=*"
    data = fetch_from_supabase(path)

    if not data:
        raise HTTPException(status_code=404, detail="لم يتم العثور على نتيجة برقم الجلوس المدخل")

    student = data[0]
    total_score = float(student.get("total_score") or 0)

    return {
        "seating_no": student.get("seating_no"),
        "name": student.get("name"),
        "total_score": total_score,
        "percentage": round((total_score / MAX_TOTAL_SCORE) * 100, 1),
        "status": student.get("school") or "ناجح",
        "school": "عام",
        "governorate": "جمهورية مصر العربية"
    }

@app.get("/api/search/name", response_model=List[SearchNameResult])
@app.get("/search/name", response_model=List[SearchNameResult])
def search_by_name(name: str = Query(..., min_length=3)):
    search_str = name.strip()
    encoded_name = urllib.parse.quote(f"*{search_str}*", safe="*")
    
    path = f"results?name=ilike.{encoded_name}&limit=15&select=*"
    data = fetch_from_supabase(path)

    if not data:
        raise HTTPException(status_code=404, detail="لم يتم العثور على نتائج بهذا الاسم")

    results = []
    for item in data:
        results.append({
            "seating_no": item.get("seating_no"),
            "name": item.get("name"),
            "total_score": float(item.get("total_score") or 0),
            "status": item.get("school") or "ناجح"
        })

    return results
