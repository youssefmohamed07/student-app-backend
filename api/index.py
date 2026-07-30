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
            # فك تشفير الرابط والكلمة المفتاحية للبحث
            parsed_url = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            q = query_params.get('q', [''])[0].strip()
            
            if not q:
                response_data = {"results": []}
                self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
                return

            # الاتصال بـ Supabase
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                response_data = {"results": [], "error": "Supabase credentials missing"}
                self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
                return

            supabase: Client = create_client(supabase_url, supabase_key)
            
            # البحث برقم الجلوس إذا كان إدخال أرقام فقط، أو بالاسم إذا كان نصاً
            if q.isdigit():
                res = supabase.table('students').select('*').eq('seating_no', int(q)).execute()
                if not res.data:
                    res = supabase.table('students').select('*').eq('roll_no', q).execute()
            else:
                res = supabase.table('students').select('*').ilike('name', f'%{q}%').limit(20).execute()

            data = res.data if res.data else []
            response_data = {"results": data}
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            # طباعة الخطأ كـ JSON مع إرجاع status 200 لتجنب انهيار الواجهة
            error_response = {"results": [], "error": str(e)}
            self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
