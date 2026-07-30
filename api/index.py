from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
import os

# محاولة استيراد Supabase بأمان
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

def normalize_text(s):
    if not s: 
        return ""
    s = str(s)
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ى', 'ي').replace('ة', 'ه')
    return s.strip().lower()

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            if not SUPABASE_AVAILABLE:
                self.wfile.write(json.dumps({"results": [], "error": "Supabase library not installed in Vercel requirements.txt"}, ensure_ascii=False).encode('utf-8'))
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
                self.wfile.write(json.dumps({"results": [], "error": "Missing SUPABASE_URL or SUPABASE_KEY in Vercel Environment Variables"}, ensure_ascii=False).encode('utf-8'))
                return

            supabase: Client = create_client(supabase_url, supabase_key)
            data = []

            # 1. البحث برقم الجلوس (إذا كان الإدخال أرقام)
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
                words = q.split()
                first_word = words[0] if words else q
                name_cols = ['name', 'student_name', 'full_name', 'fullname', 'NAME']
                
                for col in name_cols:
                    try:
                        res = supabase.table('students').select('*').ilike(col, f'%{first_word}%').limit(20).execute()
                        if res.data:
                            data = res.data
                            break
                    except Exception:
                        pass

                if data and len(words) > 1:
                    q_norm_words = [normalize_text(w) for w in words]
                    filtered = []
                    for st in data:
                        st_name = st.get('name') or st.get('student_name') or st.get('full_name') or st.get('fullname') or st.get('NAME') or ''
                        st_norm = normalize_text(st_name)
                        if all(w in st_norm for w in q_norm_words):
                            filtered.append(st)
                    if filtered:
                        data = filtered

            # 3. حساب الترتيب وعدد الطلاب بنفس المجموع لأول 5 نتائج
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
                        st['national_rank'] = st.get('national_rank', '—')

                    try:
                        same_res = supabase.table('students').select(tot_col, count='exact').eq(tot_col, tot_val).execute()
                        st['same_score_count'] = same_res.count or 1
                    except Exception:
                        st['same_score_count'] = st.get('same_score_count', '—')
                else:
                    st['national_rank'] = st.get('national_rank', '—')
                    st['same_score_count'] = st.get('same_score_count', '—')

            self.wfile.write(json.dumps({"results": data}, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"results": [], "error": str(e)}, ensure_ascii=False).encode('utf-8'))
