"""
Icerik Uretim Hatti
--------------------
Senaryo (Claude) -> Seslendirme (ElevenLabs) -> Sahne goruntuleri (Pexels)
-> Birlestirilmis video + thumbnail + metadata

KULLANIM:
1) Bu dosyayi ve config.py'yi ayni klasore koy (youtube_auth.py ile ayni klasor olabilir).
2) Terminalde kur (bir kereye mahsus):
   pip install anthropic requests moviepy pillow

3) Calistir:
   python content_pipeline.py
   (istege bagli olarak belirli bir konu vermek icin: python content_pipeline.py "kedilerde tuy yumagi")

4) Bittiginde "output" klasorunde su dosyalari bulacaksin:
   - final_video.mp4   (video)
   - thumbnail.jpg     (kapak gorseli)
   - metadata.json     (baslik / aciklama / etiketler)

   Bunlari izleyip onayladiktan sonra youtube_auth.py ile YouTube'a yukleyebiliriz.
"""

import os
import sys
import json
import random
import requests
from anthropic import Anthropic
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont

import config

OUTPUT_DIR = "output"


# ---------- 1) Senaryo uretimi ----------

def generate_script(topic_hint=None):
    client = Anthropic(api_key=config.CLAUDE_API_KEY)

    topic_line = f"Konu: {topic_hint}" if topic_hint else "Kanalin genel konusuna uygun, senin sectigin bir konu."

    prompt = f"""Sen bir veteriner hekimin YouTube kanali icin profesyonel bir icerik yazarisin.

Kanal baglami: {config.CHANNEL_TOPIC_CONTEXT}

Gorev: 60-90 saniyelik seslendirme icin kisa, profesyonel kalitede bir video senaryosu yaz.
{topic_line}

ONEMLI KURALLAR:
- Turkce dil bilgisi ve noktalama isaretlerine (nokta, virgul, soru isareti, unlem) TAM ve dogru sekilde uy.
- voiceover_text kisa, akici cumlelerden olusun; her cumle net bir noktalama isaretiyle bitsin.
  Bu, seslendirmenin dogal ve duzgun cikmasi icin kritik onemde.
- Butun senaryo TEK BIR ana hayvan turune odaklansin (orn. sadece kopek YA DA sadece kedi),
  konular karisik olmasin -- bu, sahne goruntulerinin birbiriyle tutarli/uyumlu olmasini saglar.
- voiceover_text ACIK BIR ANLATIM SIRASI izlesin: (1) dikkat cekici bir giris/soru,
  (2) durumun/sorunun aciklamasi, (3) cozum ya da bilgi, (4) kisa bir kapanis/tavsiye.
  scene_queries listesi TAM OLARAK bu sirayla, anlatilan olaylarin gerceklesme sirasina
  birebir uygun olmali -- video, anlatimla ayni kronolojik akisi izlemeli.
- Baslikta ve metinde sokak agzi/abartili gundelik ifadeler KULLANMA (orn. "cildirir",
  "resmen oldurur", "cilgin" gibi kaliplar). Veteriner hekim kimligine yakisir,
  guvenilir, sicak ama profesyonel bir dil kullan -- merak uyandirsin ama ciddiyetini korusun.

SADECE asagidaki JSON formatinda cevap ver, baska hicbir metin ekleme:
{{
  "title": "YouTube video basligi (dikkat cekici, 60 karakter alti, dogru noktalama)",
  "description": "YouTube video aciklamasi (2-3 cumle, dogru noktalama), ardindan 6-8 ilgili hashtag (# ile, orn. #veteriner #evcilhayvansagligi)",
  "tags": ["en az 18-25 SEO odakli anahtar kelime/etiket -- hem genis kapsamli (orn. 'veteriner', 'evcil hayvan', 'kopek sagligi', 'pet') hem de spesifik uzun kuyruklu etiketler kariştir, boylece video hem genis hem hedefli aramalarda cikar"],
  "voiceover_text": "Turkce, dogal ve akici konusma dilinde, dogru noktalamali tam seslendirme metni",
  "scene_queries": ["ingilizce stok video arama terimi 1", "terim 2", "terim 3", "terim 4"]
}}

scene_queries: voiceover_text'i esit parcalara bolecek sekilde 4-6 tane, HEPSI AYNI hayvan
turune ait, Pexels'te iyi sonuc verecek INGILIZCE ve SPESIFIK arama terimi uret
(orn. "golden retriever vet checkup", "dog eating bowl", "dog walking park" -- hepsi ayni tur)."""

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        raise RuntimeError("Claude yanitinda metin blogu bulunamadi.")
    text = text_blocks[0].strip()
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("\nHATA: Claude'un yaniti gecerli JSON degil. Ham yanit asagida:\n")
        print(text)
        print()
        raise


# ---------- 2) Seslendirme (ElevenLabs) ----------

def get_default_voice_id():
    resp = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
    )
    if not resp.ok:
        print(f"\nElevenLabs hata detayi (voices): {resp.text}\n")
    resp.raise_for_status()
    voices = resp.json().get("voices", [])
    if not voices:
        raise RuntimeError("ElevenLabs hesabinda hic ses bulunamadi.")
    return voices[0]["voice_id"]


def generate_voiceover(text, output_path):
    voice_id = get_default_voice_id()
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.68,
                "similarity_boost": 0.85,
                "style": 0.25,
                "use_speaker_boost": True,
            },
        },
    )
    if not resp.ok:
        print(f"\nElevenLabs hata detayi (text-to-speech): {resp.text}\n")
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)


# ---------- 3) Stok gorseller (Pexels) ----------

def fetch_stock_clip(query, output_path):
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": config.PEXELS_API_KEY},
        params={"query": query, "per_page": 5, "orientation": "landscape"},
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        return None

    # En alakali ilk 3 sonuc arasinda, Full HD'ye (1920 genislik) en yakin
    # ve onu assagi cekmeyen en kaliteli dosyayi sec.
    best_file, best_score = None, -1
    for video in videos[:3]:
        for f in video.get("video_files", []):
            width = f.get("width", 0)
            if width <= 0:
                continue
            score = width if width <= 1920 else (1920 - (width - 1920))
            if score > best_score:
                best_score = score
                best_file = f

    if not best_file:
        return None

    video_resp = requests.get(best_file["link"])
    with open(output_path, "wb") as f:
        f.write(video_resp.content)
    return output_path


def fetch_stock_photo(query, output_path):
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": config.PEXELS_API_KEY},
        params={"query": query, "per_page": 1, "orientation": "landscape"},
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    if not photos:
        return None

    photo_url = photos[0]["src"]["large"]
    photo_resp = requests.get(photo_url)
    with open(output_path, "wb") as f:
        f.write(photo_resp.content)
    return output_path


# ---------- 4) Video birlestirme ----------

def apply_safe_fade(clip, duration, fade_in=True):
    """Moviepy surumleri arasindaki API farkliliklarina karsi guvenli fade denemesi.
    Basarisiz olursa klibi degistirmeden dondurur -- render asla bu yuzden cokmez."""
    method_name = "fadein" if fade_in else "fadeout"
    if hasattr(clip, method_name):
        try:
            return getattr(clip, method_name)(duration)
        except Exception:
            pass
    try:
        from moviepy.video.fx import FadeIn, FadeOut
        effect = FadeIn(duration) if fade_in else FadeOut(duration)
        return clip.with_effects([effect])
    except Exception:
        pass
    return clip


def assemble_video(audio_path, clip_paths, output_path):
    audio = AudioFileClip(audio_path)
    total_duration = audio.duration
    per_clip = total_duration / len(clip_paths)

    segments = []
    for path in clip_paths:
        clip = VideoFileClip(path).without_audio()
        if clip.duration < per_clip:
            loops_needed = int(per_clip // clip.duration) + 1
            clip = concatenate_videoclips([clip] * loops_needed)
        clip = clip.subclipped(0, per_clip)
        segments.append(clip)

    video = concatenate_videoclips(segments, method="compose")
    video = video.with_audio(audio)

    # Profesyonel bir acilis/kapanis icin yumusak gecis
    video = apply_safe_fade(video, 0.6, fade_in=True)
    video = apply_safe_fade(video, 0.6, fade_in=False)

    video.write_videofile(
        output_path, fps=30, codec="libx264", audio_codec="aac", bitrate="8000k"
    )


# ---------- 5) Thumbnail ----------

def cover_crop(img, target_w, target_h):
    """Resmi, oranini bozmadan hedef boyutu tamamen dolduracak sekilde ortadan kirpar
    -- rastgele bir kenar dilimi yerine fotografin merkezini gosterir."""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    img = img.resize((new_w, new_h))
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def generate_thumbnail(background_path, title_text, output_path, channel_label="VETERINER HEKIM BILGI BANKASI"):
    W, H = 1280, 720
    photo = Image.open(background_path).convert("RGB")

    # Fotografi SADECE sol foto alanini, oranini bozmadan ortadan kirparak doldur
    photo_region_w = 600
    photo_cropped = cover_crop(photo, photo_region_w, H)
    img = Image.new("RGB", (W, H), (20, 20, 20))
    img.paste(photo_cropped, (0, 0))

    # Sari panel + izgara deseni icin ayri bir katman
    yellow_layer = Image.new("RGB", (W, H), (255, 212, 0))
    ydraw = ImageDraw.Draw(yellow_layer)
    grid_color = (240, 192, 0)
    for x in range(420, W, 62):
        ydraw.line([(x, 0), (x, H)], fill=grid_color, width=2)
    for y in range(0, H, 75):
        ydraw.line([(0, y), (W, y)], fill=grid_color, width=2)

    # Capraz kesimli panel siniri (maske ile)
    mask = Image.new("L", (W, H), 0)
    mdraw = ImageDraw.Draw(mask)
    panel_points = [(433, 0), (W, 0), (W, H), (546, H)]
    mdraw.polygon(panel_points, fill=255)

    img = Image.composite(yellow_layer, img, mask)
    draw = ImageDraw.Draw(img)

    def load_font(size):
        # Windows'ta (yerel test) VE Linux'ta (GitHub Actions) calisacak fontlari dene
        candidates = (
            "arialbd.ttf", "Arial Bold.ttf", "arial.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
        for name in candidates:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    panel_center_x = 913

    label_font = load_font(26)
    label_bbox = draw.textbbox((0, 0), channel_label, font=label_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    pad_x, pad_y = 28, 16
    pill_w, pill_h = label_w + pad_x * 2, label_h + pad_y * 2
    pill_y0 = 34
    draw.rounded_rectangle(
        [panel_center_x - pill_w // 2, pill_y0, panel_center_x + pill_w // 2, pill_y0 + pill_h],
        radius=pill_h // 2, fill="white",
    )
    draw.text(
        (panel_center_x, pill_y0 + pill_h / 2), channel_label,
        font=label_font, fill=(200, 16, 46), anchor="mm",
    )

    def wrap_text(text, font, max_width):
        words = text.split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:3]

    title_font = load_font(84)
    lines = wrap_text(title_text.upper(), title_font, 620)
    line_height = 96
    total_h = len(lines) * line_height
    start_y = H // 2 - total_h // 2 + line_height // 2 + 30

    for i, line in enumerate(lines):
        y = start_y + i * line_height
        draw.text(
            (panel_center_x, y), line, font=title_font, fill=(224, 52, 47),
            stroke_width=9, stroke_fill="white", anchor="mm",
        )

    img.save(output_path)


def pick_custom_thumbnail_background():
    """thumbnails/ klasorune yukledigin kendi fotograflarindan rastgele birini secer.
    Klasor yoksa ya da bossa None doner (o zaman otomatik stok gorsele dusulur)."""
    custom_dir = "thumbnails"
    if os.path.isdir(custom_dir):
        images = [
            os.path.join(custom_dir, f) for f in os.listdir(custom_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        if images:
            return random.choice(images)
    return None


# ---------- Ana akis ----------

def run_pipeline(topic_hint=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("1/5 Senaryo yaziliyor...")
    script = generate_script(topic_hint)
    print(f"    Baslik: {script['title']}")

    print("2/5 Seslendirme yapiliyor...")
    audio_path = os.path.join(OUTPUT_DIR, "narration.mp3")
    generate_voiceover(script["voiceover_text"], audio_path)

    print("3/5 Sahne goruntuleri indiriliyor...")
    clip_paths = []
    for i, q in enumerate(script["scene_queries"]):
        path = os.path.join(OUTPUT_DIR, f"clip_{i}.mp4")
        if fetch_stock_clip(q, path):
            clip_paths.append(path)
    if not clip_paths:
        raise RuntimeError("Hicbir stok video bulunamadi. Scripti tekrar calistirmayi dene.")

    print("4/5 Video birlestiriliyor (biraz surebilir)...")
    video_path = os.path.join(OUTPUT_DIR, "final_video.mp4")
    assemble_video(audio_path, clip_paths, video_path)

    print("5/5 Thumbnail olusturuluyor...")
    thumb_bg = pick_custom_thumbnail_background()
    if thumb_bg:
        print(f"    Kendi fotografin kullaniliyor: {thumb_bg}")
        generate_thumbnail(thumb_bg, script["title"], os.path.join(OUTPUT_DIR, "thumbnail.jpg"))
    else:
        stock_bg = os.path.join(OUTPUT_DIR, "thumb_bg.jpg")
        if fetch_stock_photo(script["scene_queries"][0], stock_bg):
            generate_thumbnail(stock_bg, script["title"], os.path.join(OUTPUT_DIR, "thumbnail.jpg"))

    with open(os.path.join(OUTPUT_DIR, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    print("\nTamamlandi! 'output' klasorunu kontrol et:")
    print("  - final_video.mp4")
    print("  - thumbnail.jpg")
    print("  - metadata.json")
    print("\nBeyendiysen, youtube_auth.py ile YouTube'a yukleyebiliriz.")


if __name__ == "__main__":
    topic_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(topic_arg)
