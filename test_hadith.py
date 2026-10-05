import json
import random
import urllib.request

URL = "https://raw.githubusercontent.com/AhmedBaset/hadith-json/v1.2.0/db/by_book/forties/nawawi40.json"

with urllib.request.urlopen(URL) as r:
    data = json.loads(r.read().decode("utf-8"))

h = random.choice(data["hadiths"])

print("Reference: Forty Hadith of Nawawi, Hadith", h["idInBook"])
print("Arabic:", h["arabic"].strip())
print("Narrator:", h["english"]["narrator"].strip())
print("English:", h["english"]["text"].strip())

