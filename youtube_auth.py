"""
YouTube Data API - Kimlik Dogrulama ve Video Yukleme Scripti
--------------------------------------------------------------
KULLANIM:
1) Bu dosyayi, indirdigin client_secret_....json dosyasiyla AYNI klasore koy.
2) Terminalde su kutuphaneleri kur (bir kereye mahsus):
   pip install google-auth-oauthlib google-api-python-client

3) Calistir:
   python youtube_auth.py

4) Acilan tarayici penceresinde kendi YouTube hesabinla giris yap ve izin ver.
5) Islem tamamlaninca ayni klasorde "token.pickle" dosyasi olusur.
   Bu dosya olustuktan sonra bir daha tarayici acilmaz; script otomatik
   olarak bu token'i kullanir. Bu dosyayi da client_secret dosyasi gibi
   kimseyle paylasma.
"""

import os
import glob
import json
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = "token.pickle"


def find_client_secret_file():
    matches = glob.glob("client_secret*.json")
    if not matches:
        raise FileNotFoundError(
            "client_secret_....json dosyasi bu klasorde bulunamadi. "
            "Scripti, indirdigin dosyayla ayni klasore koydugundan emin ol."
        )
    return matches[0]


def get_authenticated_service():
    # Bulutta (GitHub Actions) calisiyorsak, kimlik bilgisi bir ortam
    # degiskeninden (Secret) gelir -- tarayici acmaya gerek yoktur.
    env_creds = os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
    if env_creds:
        data = json.loads(env_creds)
        creds = Credentials(
            token=None,
            refresh_token=data["refresh_token"],
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return build("youtube", "v3", credentials=creds)

    # Yerel bilgisayarda calisiyorsak -- eskisi gibi pickle/tarayici akisi
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_secret_file = find_client_secret_file()
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def upload_video(video_path, title, description, tags=None, category_id="15", privacy_status="private"):
    """
    category_id "15" = Pets & Animals (evcil hayvan/veteriner icerigi icin uygun)
    privacy_status varsayilani "private" -- yayina hazir olana kadar kazara
    herkese acik yuklenmesin diye. Hazir oldugunda "public" yap.
    """
    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Yukleniyor: %{int(status.progress() * 100)}")

    print(f"Video yuklendi. Video ID: {response['id']}")
    return response


if __name__ == "__main__":
    # Ilk calistirmada sadece kimlik dogrulamayi tamamlamak icin:
    get_authenticated_service()
    print("Kimlik dogrulama tamamlandi. token.pickle dosyasi olusturuldu.")

    # Ornek video yukleme (hazir oldugunda asagidaki satiri aktif et):
    # upload_video("ornek_video.mp4", "Video Basligi", "Video aciklamasi",
    #              tags=["evcil hayvan", "veteriner", "pet sagligi"])
