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
    """تجريد التشكيل وتوحيد الحروف العربية للمطابقة الدقيقة"""
    if not text:
        return ""
    text = str(text)
    tashkeel = re.compile(r'[\u0617-\u061A\u064B-\u0652]')
    text = re.sub(tashkeel, '', text)
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
                self.wfile.write(json.dumps({"results": [], "error": "Supabase library missing"}, ensure_ascii=False).encode('utf-8'))
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
                self.wfile.write(json.dumps({"results": [], "error": "Missing Environment Variables"}, ensure_ascii=False).encode('utf-8'))
                return

            supabase: Client = create_client(supabase_url, supabase_key)
            data = []

            # 1. البحث برقم الجلوس (إذا كان المدخل أرقاماً فقط)
            if q.isdigit():
                val = int(q)
                try:
                    res = supabase.table('results').select('*').eq('seating_no', val).execute()
                    if res.data:
                        data = res.data
                except Exception:
                    # تحسباً لو كان seating_no مخزناً كنص وليس رقم
                    try:
                        res = supabase.table('results').select('*').eq('seating_no', str(q)).execute()
                        if res.data:
                            data = res.data
                    except Exception:
                        pass
            
            # 2. البحث بالاسم (كلمة واحدة مثل "يوسف" أو اسم كامل)
            else:
                words = q.split()
                first_word = words[0] if words else q
                
                try:
                    # البحث في جدول results بكلمة البحث في عمود name
                    res = supabase.table('results').select('*').ilike('name', f'%{first_word}%').limit(25).execute()
                    data = res.data or []
                except Exception:
                    pass

                # إذا كتب المستخدم أكثر من كلمة (مثل "يوسف محمد") نفلتر النتائج لتطابق الكل
                if data and len(words) > 1:
                    clean_q_words = [clean_arabic(w) for w in words]
                    filtered = []
                    for st in data:
                        st_name = st.get('name') or ''
                        clean_st_name = clean_arabic(st_name)
                        if all(w in clean_st_name for w in clean_q_words):
                            filtered.append(st)
                    if filtered:
                        data = filtered

            # 3. حساب الترتيب والمجموع لأول 5 نتائج
            for st in data[:5]:
                tot_val = None
                tot_col = None
                # البحث عن العمود الذي يحتوي المجموع الفعلي
                for c in ['total_degree', 'total', 'score', 'degree', 'total_score', 'degree_total']:
                    if c in st and st[c] is not None:
                        try:
                            tot_val = float(st[c])
                            tot_col = c
                            break
                        except (ValueError, TypeError):
                            pass

                if tot_val is not None and tot_col:
                    try:
                        rank_res = supabase.table('results').select(tot_col, count='exact').gt(tot_col, tot_val).execute()
                        st['national_rank'] = (rank_res.count or 0) + 1
                    except Exception:
                        st['national_rank'] = '—'

                    try:
                        same_res = supabase.table('results').select(tot_col, count='exact').eq(tot_col, tot_val).execute()
                        st['same_score_count'] = same_res.count or 1
                    except Exception:
                        st['same_score_count'] = '—'
                else:
                    st['national_rank'] = '—'
                    st['same_score_count'] = '—'

            self.wfile.write(json.dumps({"results": data}, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"results": [], "error": str(e)}, ensure_ascii=False).encode('utf-8'))
