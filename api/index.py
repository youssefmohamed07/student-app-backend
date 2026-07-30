from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
import os
import re

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

def clean_arabic(text):
    """حذف التشكيل وتوحيد الألف والياء والتاء المربوطة لضمان المطابقة 100%"""
    if not text:
        return ""
    text = str(text)
    # إزالة التشكيل والحركات العربية
    tashkeel = re.compile(r'[\u0617-\u061A\u064B-\u0652]')
    text = re.sub(tashkeel, '', text)
    # توحيد الأشكال
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ى', 'ي').replace('ة', 'ه')
    return text.strip().lower()

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            if not SUPABASE_AVAILABLE:
                self.wfile.write(json.dumps({"results": [], "error": "Supabase library missing in requirements.txt"}, ensure_ascii=False).encode('utf-8'))
                return

            parsed_url = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            q = query_params.get('q', [''])[0].strip()
            
            if not q:
                self.wfile.write(json.dumps({"results": []}, ensure_ascii=False).encode('utf-8'))
                return

            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                self.wfile.write(json.dumps({"results": [], "error": "Missing Supabase Environment Variables"}, ensure_ascii=False).encode('utf-8'))
                return

            supabase: Client = create_client(supabase_url, supabase_key)
            data = []

            # 1. البحث برقم الجلوس (إذا كان إدخال أرقام)
            if q.isdigit():
                seating_cols = ['seating_no', 'seating_number', 'roll_no', 'seat_no', 'id']
                for col in seating_cols:
                    try:
                        val = int(q) if col != 'roll_no' else q
                        res = supabase.table('students').select('*').eq(col, val).execute()
                        if res.data:
                            data = res.data
                            break
                    except Exception:
                        pass
            
            # 2. البحث بالاسم
            else:
                clean_q = clean_arabic(q)
                q_words = clean_q.split()
                first_word = q_words[0] if q_words else q

                # المحاولة الأولى: ilike
                name_cols = ['name', 'student_name', 'full_name', 'fullname', 'NAME']
                for col in name_cols:
                    try:
                        res = supabase.table('students').select('*').ilike(col, f'%{first_word}%').limit(50).execute()
                        if res.data:
                            data = res.data
                            break
                    except Exception:
                        pass

                # المحاولة الثانية (Fallback): جلب عينة والتصفية في بايثون بالاسم المنظّف
                if not data:
                    try:
                        res = supabase.table('students').select('*').limit(300).execute()
                        if res.data:
                            all_records = res.data
                            matched = []
                            for rec in all_records:
                                rec_name = rec.get('name') or rec.get('student_name') or rec.get('full_name') or rec.get('fullname') or rec.get('NAME') or ''
                                clean_rec_name = clean_arabic(rec_name)
                                if all(w in clean_rec_name for w in q_words):
                                    matched.append(rec)
                            data = matched
                    except Exception:
                        pass

                # تصفية دقيقة إضافية عند كتابة أكثر من كلمة
                elif len(data) > 1 and len(q_words) > 1:
                    filtered = []
                    for rec in data:
                        rec_name = rec.get('name') or rec.get('student_name') or rec.get('full_name') or rec.get('fullname') or rec.get('NAME') or ''
                        clean_rec_name = clean_arabic(rec_name)
                        if all(w in clean_rec_name for w in q_words):
                            filtered.append(rec)
                    if filtered:
                        data = filtered

            # 3. حساب الترتيب وعدد الطلاب بنفس المجموع (لأول 5 نتائج)
            for st in data[:5]:
                tot_val = None
                tot_col = None
                for c in ['total_degree', 'total', 'score', 'degree', 'total_score']:
                    if c in st and st[c] is not None:
                        try:
                            tot_val = float(st[c])
                            tot_col = c
                            break
                        except (ValueError, TypeError):
                            pass

                if tot_val is not None and tot_col:
                    try:
                        rank_res = supabase.table('students').select(tot_col, count='exact').gt(tot_col, tot_val).execute()
                        st['national_rank'] = (rank_res.count or 0) + 1
                    except Exception:
                        st['national_rank'] = '—'

                    try:
                        same_res = supabase.table('students').select(tot_col, count='exact').eq(tot_col, tot_val).execute()
                        st['same_score_count'] = same_res.count or 1
                    except Exception:
                        st['same_score_count'] = '—'
                else:
                    st['national_rank'] = '—'
                    st['same_score_count'] = '—'

            self.wfile.write(json.dumps({"results": data}, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"results": [], "error": str(e)}, ensure_ascii=False).encode('utf-8'))
