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
                self.wfile.write(json.dumps({"results": [], "error": "مكتبة supabase غير مثبتة في requirements.txt"}, ensure_ascii=False).encode('utf-8'))
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
                self.wfile.write(json.dumps({"results": [], "error": "المتغيرات البيئية لـ Supabase مفقودة"}, ensure_ascii=False).encode('utf-8'))
                return

            supabase: Client = create_client(supabase_url, supabase_key)
            raw_data = []

            # 1. البحث برقم الجلوس
            if q.isdigit():
                val = int(q)
                try:
                    res = supabase.table('results').select('*').eq('seating_no', val).execute()
                    if res.data:
                        raw_data = res.data
                except Exception:
                    try:
                        res = supabase.table('results').select('*').eq('seating_no', str(q)).execute()
                        if res.data:
                            raw_data = res.data
                    except Exception:
                        pass
            
            # 2. البحث بالاسم
            else:
                words = q.split()
                first_word = words[0] if words else q
                
                try:
                    res = supabase.table('results').select('*').ilike('name', f'{first_word}%').limit(25).execute()
                    raw_data = res.data or []
                except Exception:
                    pass

                if not raw_data:
                    try:
                        res = supabase.table('results').select('*').ilike('name', f'%{first_word}%').limit(25).execute()
                        raw_data = res.data or []
                    except Exception:
                        pass

                if raw_data and len(words) > 1:
                    clean_q_words = [clean_arabic(w) for w in words]
                    filtered = []
                    for st in raw_data:
                        st_name = st.get('name') or ''
                        clean_st_name = clean_arabic(st_name)
                        if all(w in clean_st_name for w in clean_q_words):
                            filtered.append(st)
                    if filtered:
                        raw_data = filtered

            formatted_results = []

            # 3. توحيد قراءة البيانات وحساب الترتيب والدرجات المفقودة بناءً على مجموع 320
            for st in raw_data[:5]:
                tot_val = None
                tot_col = None

                for k, v in st.items():
                    if k not in ['seating_no', 'id'] and v is not None:
                        try:
                            v_float = float(v)
                            if 0 <= v_float <= 320:
                                tot_val = v_float
                                tot_col = k
                                break
                        except (ValueError, TypeError):
                            pass

                national_rank = '—'
                same_score_count = '—'

                if tot_val is not None and tot_col:
                    try:
                        rank_res = supabase.table('results').select(tot_col, count='exact').gt(tot_col, tot_val).execute()
                        national_rank = (rank_res.count or 0) + 1
                    except Exception:
                        pass

                    try:
                        same_res = supabase.table('results').select(tot_col, count='exact').eq(tot_col, tot_val).execute()
                        same_score_count = same_res.count or 1
                    except Exception:
                        pass

                # حساب النسبة المئوية والدرجات المفقودة من 320
                pct_val = round((tot_val / 320.0) * 100, 2) if tot_val is not None else '—'
                lost_marks = round(320.0 - tot_val, 1) if tot_val is not None else '—'

                formatted_results.append({
                    "name": st.get('name') or 'طالب ثانوية عامة',
                    "seating_no": st.get('seating_no') or q,
                    "total": tot_val if tot_val is not None else '—',
                    "lost_marks": lost_marks,
                    "percentage": f"{pct_val}%" if pct_val != '—' else '—',
                    "pct_num": pct_val if pct_val != '—' else 0,
                    "national_rank": national_rank,
                    "same_score_count": same_score_count,
                    "status": st.get('school') or st.get('status') or 'ناجح',
                    "branch": st.get('branch') or 'عام'
                })

            self.wfile.write(json.dumps({"results": formatted_results}, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"results": [], "error": f"خطأ في السيرفر: {str(e)}"}, ensure_ascii=False).encode('utf-8'))
