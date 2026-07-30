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

            # 1. إذا كان البحث برقم الجلوس (أرقام فقط)
            if q.isdigit():
                val = int(q)
                try:
                    # البحث في أعمدة أرقام الجلوس المختلفة
                    res = supabase.table('students').select('*').or_(
                        f"seating_no.eq.{val},seating_number.eq.{val},roll_no.eq.{q},seat_no.eq.{val}"
                    ).execute()
                    data = res.data or []
                except Exception:
                    # تجربة استعلام مباشر إذا فشل الاستعلام المجمع
                    for col in ['seating_no', 'seating_number', 'roll_no', 'seat_no']:
                        try:
                            res = supabase.table('students').select('*').eq(col, val if col != 'roll_no' else q).execute()
                            if res.data:
                                data = res.data
                                break
                        except Exception:
                            pass
            
            # 2. إذا كان البحث باسم الطالب (كلمة واحدة مثل "يوسف" أو اسم كامل)
            else:
                words = q.split()
                # البحث بالكلمة الأولى أو الجملة كاملة بنفس المرونة
                search_term = words[0] if len(words) == 1 else q
                
                try:
                    # بحث موحد في كل أعمدة الأسماء المحتملة بنفس الوقت
                    or_query = f"name.ilike.*{search_term}*,student_name.ilike.*{search_term}*,full_name.ilike.*{search_term}*,fullname.ilike.*{search_term}*"
                    res = supabase.table('students').select('*').or_(or_query).limit(30).execute()
                    data = res.data or []
                except Exception:
                    pass

                # إذا أدخل المستخدم أكثر من كلمة (مثلاً: يوسف محمد)، نفلتر النتائج لتطابق الكلمتين معاً
                if data and len(words) > 1:
                    clean_q_words = [clean_arabic(w) for w in words]
                    filtered = []
                    for st in data:
                        st_name = st.get('name') or st.get('student_name') or st.get('full_name') or st.get('fullname') or ''
                        clean_st_name = clean_arabic(st_name)
                        if all(w in clean_st_name for w in clean_q_words):
                            filtered.append(st)
                    if filtered:
                        data = filtered

            # 3. حساب الترتيب وعدد الطلاب بنفس المجموع بأمان
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
