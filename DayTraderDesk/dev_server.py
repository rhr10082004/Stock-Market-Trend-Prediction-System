from http.server import HTTPServer

from api._lib.market import handler


if __name__ == "__main__":
    print("Market API listening on http://127.0.0.1:8000")
    HTTPServer(("127.0.0.1", 8000), handler).serve_forever()
