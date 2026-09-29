import requests

r = requests.get(
    "http://127.0.0.1:8001/day",
    params={"date": "2026-05-01"},
    headers={"Authorization": "SECRET"}
)

print(r.json())
