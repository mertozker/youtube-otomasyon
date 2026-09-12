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

SADECE asagidaki JSON formatinda cevap ver, baska hicbir metin ekleme:
{{
  "title": "YouTube video basligi (dikkat cekici, 60 karakter alti, dogru noktalama)",
  "description": "YouTube video aciklamasi (2-3 cumle, dogru noktalama), ardindan 6-8 ilgili hashtag (# ile, orn. #veteriner #evcilhayvansagligi)",
  "tags": ["en az 12-15 SEO odakli anahtar kelime/etiket"],
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

    files = sorted(videos[0]["video_files"], key=lambda f: f.get("width", 0), reverse=True)
    hd_file = next((f for f in files if f.get("width", 0) <= 1920), files[-1])

    video_resp = requests.get(hd_file["link"])
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
    video.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac")


# ---------- 5) Thumbnail ----------

def generate_thumbnail(background_path, title_text, output_path, badge_text="VETERINER ACIKLIYOR"):
    img = Image.open(background_path).convert("RGBA").resize((1280, 720))

    # Tum goruntuyu hafifce karart (metin kontrastini artirir)
    dark_overlay = Image.new("RGBA", img.size, (0, 0, 0, 90))
    img = Image.alpha_composite(img, dark_overlay)

    # Alt kisimda baslik icin daha koyu bir bant
    bottom_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(bottom_overlay)
    bdraw.rectangle([0, 420, 1280, 720], fill=(0, 0, 0, 175))
    img = Image.alpha_composite(img, bottom_overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    def load_font(size):
        for name in ("impact.ttf", "arialbd.ttf", "Arial Bold.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    title_font = load_font(76)
    badge_font = load_font(32)

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
        return lines[:3]  # en fazla 3 satir, tasmayi onler

    lines = wrap_text(title_text.upper(), title_font, 1180)
    line_height = 84
    start_y = 700 - (len(lines) * line_height)
    ACCENT_COLOR = (255, 219, 0)  # dikkat cekici sari -- merak uyandiran kelime icin

    for i, line in enumerate(lines):
        y = start_y + i * line_height
        words = line.split()

        if i == len(lines) - 1 and len(words) > 1:
            normal_part = " ".join(words[:-1]) + " "
            highlight_word = words[-1]
        else:
            normal_part = line
            highlight_word = None

        draw.text(
            (48, y), normal_part, font=title_font, fill="white",
            stroke_width=6, stroke_fill="black",
        )

        if highlight_word:
            normal_bbox = draw.textbbox((48, y), normal_part, font=title_font, stroke_width=6)
            draw.text(
                (normal_bbox[2], y), highlight_word, font=title_font, fill=ACCENT_COLOR,
                stroke_width=6, stroke_fill="black",
            )

    # Merak uyandirici rozet (sag ust kose)
    padding_x, padding_y = 24, 14
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = (bbox[2] - bbox[0]) + padding_x * 2
    badge_h = (bbox[3] - bbox[1]) + padding_y * 2
    badge_x0, badge_y0 = 1280 - badge_w - 30, 30
    draw.rounded_rectangle(
        [badge_x0, badge_y0, badge_x0 + badge_w, badge_y0 + badge_h],
        radius=16, fill=(255, 209, 0),
    )
    draw.text(
        (badge_x0 + padding_x, badge_y0 + padding_y - bbox[1]),
        badge_text, font=badge_font, fill="black",
    )

    img.save(output_path)


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
    thumb_bg = os.path.join(OUTPUT_DIR, "thumb_bg.jpg")
    if fetch_stock_photo(script["scene_queries"][0], thumb_bg):
        generate_thumbnail(thumb_bg, script["title"], os.path.join(OUTPUT_DIR, "thumbnail.jpg"))

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
