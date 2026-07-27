#!/usr/bin/env python3
import http.server
import json
import time
import requests

class PingHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/ping':
            latency_ms = self.http_ping()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            response = json.dumps({'latency': latency_ms})
            self.wfile.write(response.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def http_ping(self, url='https://music.yandex.ru/favicon.ico', timeout=5):
        try:
            start = time.time()
            # Выполняем GET-запрос, не следуем за редиректами
            r = requests.get(url, timeout=timeout, allow_redirects=False)
            end = time.time()
            if r.status_code == 200:
                return round((end - start) * 1000)
            else:
                return -1  # код ответа не 200
        except Exception:
            return -1  # ошибка соединения

    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', 61210), PingHandler)
    server.serve_forever()
