from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
import os
from supabase import create_client, Client

def normalize_arabic(text):
    """تطنيش وتوحيد الهمزات والياءات لضمان التطابق"""
    if not text:
        return ""
    text = str(text)
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ى', 'ي').replace('ة', 'ه')
    return text.strip().lower()

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            q = query_params.get('q', [''])[0].strip()
            
            if not q:
                self.wfile.write(json.dumps({"results": []}, ensure_ascii=False).encode('utf-8'))
                return

            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                self.wfile.write(json.dumps({"results": [], "error": "Supabase key missing"}, ensure_ascii=False).encode('utf-8'))
                return

            supabase: Client = create_client(supabase_url, supabase_key)
            data = []

            # 1. إذا كان البحث برقم الجلوس
            if q.isdigit():
                for col in ['seating_no', 'roll_no', 'seat_no']:
                    try:
                        val = int(q) if col != 'roll_no' else q
                        res = supabase.table('students').select('*').eq(col, val).execute()
                        if res.data:
                            data = res.data
                            break
                    except:
                        pass
            
            # 2. إذا كان البحث باسم الطالب
            else:
                words = q.split()
                first_word = words[0]
                raw_data = []

                for name_col in ['name', 'student_name', 'NAME']:
                    try:
                        res = supabase.table('students').select('*').ilike(name_col, f'%{first_word}%').limit(30).execute()
                        if res.data:
                            raw_data = res.data
                            break
                    except:
                        pass

                if raw_data:
                    query_words = normalize_arabic(q).split()
                    filtered = []
                    for student in raw_data:
                        s_name = student.get('name') or student.get('student_name') or student.get('NAME') or ''
                        norm_s_name = normalize_arabic(s_name)
                        if all(w in norm_s_name for w in query_words):
                            filtered.append(student)
                    data = filtered if filtered else raw_data

            # 3. إثراء البيانات بـ (الترتيب على الجمهورية + عدد الطلاب بنفس المجموع)
            for student in data:
                tot = student.get('total_degree') or student.get('total') or student.get('score') or student.get('degree')
                
                if tot is not None:
                    try:
                        tot_val = float(tot)
                        
                        # حساب الترتيب على الجمهورية
                        try:
                            rank_res = supabase.table('students').select('id', count='exact').gt('total_degree', tot_val).execute()
                            student['national_rank'] = (rank_res.count or 0) + 1
                        except:
                            student['national_rank'] = student.get('national_rank') or student.get('rank') or '—'

                        # حساب عدد الطلاب الحاصلين على نفس المجموع
                        try:
                            same_res = supabase.table('students').select('id', count='exact').eq('total_degree', tot_val).execute()
                            student['same_score_count'] = same_res.count or 1
                        except:
                            student['same_score_count'] = student.get('same_score_count') or '—'
                            
                    except ValueError:
                        student['national_rank'] = '—'
                        student['same_score_count'] = '—'

            self.wfile.write(json.dumps({"results": data}, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"results": [], "error": str(e)}, ensure_ascii=False).encode('utf-8'))
