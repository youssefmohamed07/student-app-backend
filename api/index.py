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
                self.wfile.write(json.dumps({"results": [], "error": "المتغيرات SUPABASE_URL أو SUPABASE_KEY غير موجودة في Vercel"}, ensure_ascii=False).encode('utf-8'))
                return

            supabase: Client = create_client(supabase_url, supabase_key)
            data = []

            # 1. البحث برقم الجلوس (سريع جداً)
            if q.isdigit():
                val = int(q)
                try:
                    res = supabase.table('results').select('*').eq('seating_no', val).execute()
                    if res.data:
                        data = res.data
                except Exception:
                    try:
                        res = supabase.table('results').select('*').eq('seating_no', str(q)).execute()
                        if res.data:
                            data = res.data
                    except Exception:
                        pass
            
            # 2. البحث بالاسم (مُحسّن لقواعد البيانات الضخمة)
            else:
                words = q.split()
                first_word = words[0] if words else q
                
                # البحث ببدء الاسم بالكلمة أولاً (سريع جداً في PostgreSQL)
                try:
                    res = supabase.table('results').select('*').ilike('name', f'{first_word}%').limit(20).execute()
                    data = res.data or []
                except Exception:
                    pass

                # إذا لم تجد نتائج، تجربة البحث في أي مكان بالاسم
                if not data:
                    try:
                        res = supabase.table('results').select('*').ilike('name', f'%{first_word}%').limit(20).execute()
                        data = res.data or []
                    except Exception:
                        pass

                # إذا أدخل المستخدم أكثر من كلمة (مثل "عمر محمد") يتم الفلترة بدقة
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

            # 3. إعداد بيانات العرض
            for st in data[:5]:
                st['national_rank'] = st.get('national_rank', '—')
                st['same_score_count'] = st.get('same_score_count', '—')

            self.wfile.write(json.dumps({"results": data}, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"results": [], "error": f"خطأ في السيرفر: {str(e)}"}, ensure_ascii=False).encode('utf-8'))
