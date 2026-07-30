from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
import os
from supabase import create_client, Client

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

            # 1. إذا كان الإدخال أرقام فقط (رقم جلوس)
            if q.isdigit():
                try:
                    res = supabase.table('students').select('*').eq('seating_no', int(q)).execute()
                    data = res.data or []
                except:
                    pass

                if not data:
                    try:
                        res = supabase.table('students').select('*').eq('roll_no', q).execute()
                        data = res.data or []
                    except:
                        pass
            
            # 2. إذا كان الإدخال نصاً (اسم الطالب)
            else:
                try:
                    res = supabase.table('students').select('*').ilike('name', f'%{q}%').limit(20).execute()
                    data = res.data or []
                except:
                    pass

                if not data:
                    try:
                        res = supabase.table('students').select('*').ilike('student_name', f'%{q}%').limit(20).execute()
                        data = res.data or []
                    except:
                        pass

            self.wfile.write(json.dumps({"results": data}, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self.wfile.write(json.dumps({"results": [], "error": str(e)}, ensure_ascii=False).encode('utf-8'))
