"""
Video Yayinlama Scripti
------------------------
content_pipeline.py tarafindan uretilen video + metadata'yi okuyup
YouTube'a "private" (sadece sen gorursun) olarak yukler ve kapak
gorselini (thumbnail) ayarlar.

KULLANIM:
1) Once content_pipeline.py'yi calistirip bir video uret.
2) output/final_video.mp4, output/thumbnail.jpg dosyalarini izleyip
   begendiysen, bu scripti calistir:
   python publish_video.py

Video YouTube'a "private" olarak yuklenir -- kimse gormez, sadece sen.
studio.youtube.com adresine girip videoyu son kez inceleyip "Public"
yaptiginda herkese acik olur.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from googleapiclient.http import MediaFileUpload
from youtube_auth import get_authenticated_service
import config

OUTPUT_DIR = "output"


def send_email_notification(subject, body):
    if not getattr(config, "GMAIL_APP_PASSWORD", ""):
        print("(E-posta ayarlanmamis, bildirim atlaniyor.)")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = config.NOTIFY_EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        server.send_message(msg)


def set_thumbnail(youtube, video_id, thumbnail_path):
    if not os.path.exists(thumbnail_path):
        print("(Thumbnail dosyasi bulunamadi, atlaniyor.)")
        return
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path),
    ).execute()


def sanitize_tags(tags, max_total_chars=460):
    """YouTube etiketler icin toplam ~500 karakter siniri koyuyor -- fazlasi
    yuklemeyi hatayla basarisiz kilabilir. Onemli/genis etiketler basta kalsin
    diye siradan kesiyoruz."""
    result, total = [], 0
    for t in (tags or []):
        t = t.strip()
        if not t:
            continue
        added = len(t) + 1
        if total + added > max_total_chars:
            break
        result.append(t)
        total += added
    return result


def publish():
    metadata_path = os.path.join(OUTPUT_DIR, "metadata.json")
    video_path = os.path.join(OUTPUT_DIR, "final_video.mp4")
    thumbnail_path = os.path.join(OUTPUT_DIR, "thumbnail.jpg")

    if not os.path.exists(metadata_path) or not os.path.exists(video_path):
        raise FileNotFoundError(
            "output/metadata.json veya output/final_video.mp4 bulunamadi. "
            "Once content_pipeline.py'yi calistirdigindan emin ol."
        )

    with open(metadata_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    print(f"Yukleniyor: {script['title']}")

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": script["title"],
            "description": script.get("description", ""),
            "tags": sanitize_tags(script.get("tags", [])),
            "categoryId": "15",  # Pets & Animals
        },
        "status": {
            "privacyStatus": "private",  # sen onaylayana kadar kimse gormez
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Yukleniyor: %{int(status.progress() * 100)}")

    video_id = response["id"]
    print("\nVideo yuklendi (PRIVATE -- su an sadece sen goruyorsun).")

    print("Kapak gorseli ayarlaniyor...")
    try:
        set_thumbnail(youtube, video_id, thumbnail_path)
        print("Thumbnail ayarlandi.")
    except Exception as e:
        print(f"Thumbnail ayarlanamadi (video yine de yuklendi): {e}")

    review_link = f"https://studio.youtube.com/video/{video_id}/edit"
    print(f"\nIncelemek icin: {review_link}")
    print("Begendiysen, oradan durumu 'Public' yaparak yayina alabilirsin.")

    try:
        send_email_notification(
            subject=f"Yeni video onayini bekliyor: {script['title']}",
            body=(
                f"Yeni bir video uretildi ve YouTube'a private olarak yuklendi.\n\n"
                f"Baslik: {script['title']}\n\n"
                f"Incelemek icin: {review_link}\n\n"
                f"Begendiysen 'Public' yaparak yayinlayabilirsin."
            ),
        )
        print("Bildirim e-postasi gonderildi.")
    except Exception as e:
        print(f"E-posta gonderilemedi (video yine de yuklendi): {e}")


if __name__ == "__main__":
    publish()
