from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse
import ssl

SUPABASE_URL = "https://znewxywawcpibiodmtnj.supabase.co"
SUPABASE_KEY = "sb_publishable_s2MTJ7z1DhS-PlWz1zwvGw_lKh7bb1P"
MAX_TOTAL_SCORE = 320.0

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def fetch_from_supabase(endpoint_path):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint_path}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return None

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

        # الاستعلام برقم الجلوس
        if "/api/result/" in path or "/result/" in path:
            seating_no = path.split("/")[-1].strip()
            if not seating_no.isdigit():
                response_data = {"detail": "رقم الجلوس يجب أن يتكون من أرقام فقط"}
            else:
                data = fetch_from_supabase(f"results?seating_no=eq.{seating_no}&select=*")
                if not data:
                    response_data = {"detail": "لم يتم العثور على نتيجة برقم الجلوس المدخل"}
                else:
                    student = data[0]
                    total = float(student.get("total_score") or 0)
                    response_data = {
                        "seating_no": student.get("seating_no"),
                        "name": student.get("name"),
                        "total_score": total,
                        "percentage": round((total / MAX_TOTAL_SCORE) * 100, 1),
                        "status": student.get("school") or "ناجح",
                        "school": "عام",
                        "governorate": "جمهورية مصر العربية"
                    }
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
            return

        # الاستعلام بالاسم
        if "/api/search/name" in path or "/search/name" in path:
            name_list = query_params.get("name", [""])
            name_str = name_list[0].strip()
            if len(name_str) < 3:
                response_data = {"detail": "الرجاء كتابة 3 أحرف على الأقل للبحث"}
            else:
                encoded_name = urllib.parse.quote(f"*{name_str}*", safe="*")
                data = fetch_from_supabase(f"results?name=ilike.{encoded_name}&limit=15&select=*")
                if not data:
                    response_data = {"detail": "لم يتم العثور على نتائج بهذا الاسم"}
                else:
                    results = []
                    for item in data:
                        results.append({
                            "seating_no": item.get("seating_no"),
                            "name": item.get("name"),
                            "total_score": float(item.get("total_score") or 0),
                            "status": item.get("school") or "ناجح"
                        })
                    response_data = results
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
            return

        response_data = {"detail": "مسار غير صالح"}
        self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
