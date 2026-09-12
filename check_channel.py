"""
Hangi YouTube kanalina bagli olduguni gosteren kontrol scripti.
Video yuklemeden once dogru kanala bagli oldugunu teyit etmek icin kullan.

KULLANIM:
   python check_channel.py
"""

from youtube_auth import get_authenticated_service

youtube = get_authenticated_service()
response = youtube.channels().list(part="snippet", mine=True).execute()

items = response.get("items", [])
if not items:
    print("Hicbir kanal bulunamadi.")
else:
    for item in items:
        print(f"Bagli oldugun kanal: {item['snippet']['title']}  (ID: {item['id']})")
