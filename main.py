"""
نتيجة الثانوية العامة 2026 — Full Stack App (FastAPI + HTML)
===========================================================
"""

import os
import traceback
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

DEFAULT_URL = "https://znewxywawcpibiodmtnj.supabase.co"
DEFAULT_KEY = "sb_publishable_s2MTJ7z1DhS-PlWz1zwvGw_lKh7bb1P"

SUPABASE_URL = os.environ.get("SUPABASE_URL") or DEFAULT_URL
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or DEFAULT_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
MAX_TOTAL_SCORE = 320.0

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Thanaweya Amma 2026 Web Portal")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = (
    ["*"] if allowed_origins_env.strip() == "*" else [o.strip() for o in allowed_origins_env.split(",")]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Frontend Route (عرض الواجهة الأساسية)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h2>خطأ: ملف index.html غير موجود في مجلد المشروع الرئيسي.</h2>"

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class StudentResult(BaseModel):
    seating_no: int
    name: str
    total_score: float
    percentage: float
    status: str
    school: Optional[str] = None
    governorate: Optional[str] = None
    same_score_count: int
    rank: int
    total_students: int

class SearchNameResult(BaseModel):
    seating_no: int
    name: str
    total_score: float
    status: str

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
_total_students_cache: Optional[int] = None

def get_total_students() -> int:
    global _total_students_cache
    if _total_students_cache is not None and _total_students_cache > 0:
        return _total_students_cache
    try:
        res = supabase.table("results").select("seating_no", count="exact").limit(1).execute()
        _total_students_cache = res.count or 0
    except Exception as e:
        print(f"[warn] Total students query failed: {e}")
        _total_students_cache = 0
    return _total_students_cache

def _enrich_student(student: dict) -> dict:
    total_score = float(student.get("total_score") or 0)

    # 1. حساب عدد الطلاب بنفس المجموع
    same_score_count = 1
    try:
        rpc_res = supabase.rpc("get_same_score_count", {"score_val": total_score}).execute()
        if rpc_res.data is not None:
            same_score_count = rpc_res.data
        else:
            res = supabase.table("results").select("seating_no", count="exact").eq("total_score", total_score).execute()
            if res.count is not None and res.count > 0:
                same_score_count = res.count
    except Exception:
        try:
            res = supabase.table("results").select("seating_no", count="exact").eq("total_score", total_score).execute()
            if res.count is not None and res.count > 0:
                same_score_count = res.count
        except Exception as e:
            print(f"[warn] same_score_count failed: {e}")

    # 2. حساب الترتيب الفعلي
    rank = 1
    try:
        rpc_rank = supabase.rpc("get_student_rank", {"score_val": total_score}).execute()
        if rpc_rank.data is not None:
            rank = rpc_rank.data
        else:
            res = supabase.table("results").select("seating_no", count="exact").gt("total_score", total_score).execute()
            if res.count is not None:
                rank = res.count + 1
    except Exception:
        try:
            res = supabase.table("results").select("seating_no", count="exact").gt("total_score", total_score).execute()
            if res.count is not None:
                rank = res.count + 1
        except Exception as e:
            print(f"[warn] rank query failed: {e}")

    total_students = get_total_students()
    
    status_val = (
        student.get("status") 
        or student.get("student_case") 
        or student.get("case") 
        or "ناجح دور أول"
    )

    return {
        "seating_no": student.get("seating_no"),
        "name": student.get("name"),
        "total_score": total_score,
        "percentage": round((total_score / MAX_TOTAL_SCORE) * 100, 1),
        "status": status_val,
        "school": student.get("school"),
        "governorate": student.get("governorate"),
        "same_score_count": same_score_count,
        "rank": rank,
        "total_students": total_students,
    }

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/result/{seating_no}", response_model=StudentResult)
@limiter.limit("30/minute")
def get_result(request: Request, seating_no: str):
    seating_no = seating_no.strip()
    if not seating_no.isdigit():
        raise HTTPException(status_code=400, detail="رقم الجلوس يجب أن يتكون من أرقام فقط")

    try:
        response = (
            supabase.table("results")
            .select("*")
            .eq("seating_no", int(seating_no))
            .limit(1)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="لم يتم العثور على نتيجة برقم الجلوس المدخل")

        student = response.data[0]
        return _enrich_student(student)

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n--- ERROR ---\n{traceback.format_exc()}\n-------------")
        raise HTTPException(status_code=500, detail=f"خطأ في قاعدة البيانات: {str(e)}")

@app.get("/api/search/name", response_model=List[SearchNameResult])
@limiter.limit("20/minute")
def search_by_name(request: Request, name: str = Query(..., min_length=3)):
    search_str = name.strip()
    try:
        response = (
            supabase.table("results")
            .select("*")
            .ilike("name", f"{search_str}%")
            .limit(10)
            .execute()
        )
        if not response.data:
            response = (
                supabase.table("results")
                .select("*")
                .ilike("name", f"%{search_str}%")
                .limit(10)
                .execute()
            )

        if not response.data:
            raise HTTPException(status_code=404, detail="لم يتم العثور على نتائج بهذا الاسم")

        results = []
        for item in response.data:
            results.append({
                "seating_no": item.get("seating_no"),
                "name": item.get("name"),
                "total_score": float(item.get("total_score") or 0),
                "status": item.get("status") or item.get("student_case") or "ناجح دور أول"
            })

        return results

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n--- ERROR ---\n{traceback.format_exc()}\n-------------")
        err_str = str(e).lower()
        if "57014" in err_str or "timeout" in err_str:
            raise HTTPException(
                status_code=504,
                detail="البحث استغرق وقتًا طويلاً، يرجى كتابة الاسم بشكل أكمل لتضييق نطاق البحث.",
            )
        raise HTTPException(status_code=500, detail=f"خطأ في قاعدة البيانات: {str(e)}")

@app.get("/api/stats")
def get_stats():
    try:
        total = get_total_students()
        return {"total": total, "status_counts": {}}
    except Exception as e:
        print(f"\n--- ERROR ---\n{traceback.format_exc()}\n-------------")
        raise HTTPException(status_code=500, detail=f"خطأ في قاعدة البيانات: {str(e)}")