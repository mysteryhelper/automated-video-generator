import os
import time
import requests
import subprocess
from elevenlabs.client import ElevenLabs

# --- API Credentials from Environment ---
AGNES_API_KEY = os.getenv("AGNES_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
UPLOAD_POST_API_KEY = os.getenv("UPLOAD_POST_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Free key from Google AI Studio

AGNES_BASE_URL = "https://agnes-ai.com"
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # "George" voice ID

def generate_ai_script_and_metadata():
    """Uses Google Gemini via AI Studio free tier to brainstorm unique content daily."""
    print("🤖 Prompting Gemini for a new script and video parameters...")
    
    url = f"https://googleapis.com{GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = (
        "You are an AI video strategist. Generate content for a 15-second sci-fi short video.\n"
        "Provide your output exactly in this format with zero extra text or pleasantries:\n"
        "TITLE: [Catchy viral title with hashtags]\n"
        "PROMPT: [Detailed text-to-video visual prompt for an image generator, under 40 words]\n"
        "SCRIPT: [A brief, cinematic 2-sentence voiceover narration under 30 words total]"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    raw_response_text = response.json()['candidates'][0]['content']['parts'][0]['text']
    
    parsed_data = {}
    for line in raw_response_text.split('\n'):
        if line.startswith("TITLE:"):
            parsed_data["title"] = line.replace("TITLE:", "").strip()
        elif line.startswith("PROMPT:"):
            parsed_data["prompt"] = line.replace("PROMPT:", "").strip() + ", cinematic, vertical 9:16 format"
        elif line.startswith("SCRIPT:"):
            parsed_data["script"] = line.replace("SCRIPT:", "").strip()
            
    return parsed_data

def generate_video_segment(visual_prompt):
    """Requests a baseline video from Agnes AI and polls until completion."""
    print(f"🎬 Requesting video from Agnes AI with prompt: {visual_prompt}")
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "agnes-video-v2.0", "prompt": visual_prompt, "frame_rate": 24}
    
    response = requests.post(f"{AGNES_BASE_URL}/video/generate", json=payload, headers=headers)
    response.raise_for_status()
    task_id = response.json().get("task_id") or response.json().get("video_id")
    
    for _ in range(30):
        time.sleep(10)
        status_res = requests.get(f"{AGNES_BASE_URL}/tasks/{task_id}", headers=headers)
        if status_res.json().get("status") == "COMPLETED":
            return status_res.json()["output"]["video_url"]
    raise TimeoutError("Agnes AI video generation timed out.")

def generate_voiceover(script_text):
    """Generates speech track from text via ElevenLabs API."""
    print(f"🎙️ Sending script to ElevenLabs: '{script_text}'")
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    audio_stream = client.text_to_speech.convert(
        text=script_text, voice_id=VOICE_ID, model_id="eleven_v3"
    )
    with open("voiceover.mp3", "wb") as f:
        for chunk in audio_stream:
            f.write(chunk)

def publish_to_socials(filepath, video_title):
    """Publishes the final compiled video file directly to TikTok and YouTube Shorts."""
    print(f"🚀 Publishing to social platforms with title: {video_title}")
    url = "https://upload-post.com"
    headers = {"Authorization": f"Bearer {UPLOAD_POST_API_KEY}"}
    data = {"title": video_title, "platforms[]": ["youtube", "tiktok"], "youtube_shorts": "true"}
    
    with open(filepath, "rb") as video_file:
        files = {"file": video_file}
        response = requests.post(url, headers=headers, data=data, files=files)
        print("Publishing Response:", response.json())

def main():
    # 1. Generate unique scripts and prompts via free LLM
    ai_generation = generate_ai_script_and_metadata()
    
    # 2. Compile video from generated values
    video_url = generate_video_segment(ai_generation["prompt"])
    with open("temp_input.mp4", "wb") as f:
        f.write(requests.get(video_url).content)
        
    generate_voiceover(ai_generation["script"])
    
    # 3. Stitch audio/video assets using system FFMPEG
    output_filename = "final_output_production.mp4"
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", "temp_input.mp4", "-i", "voiceover.mp3",
        "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
        "-shortest", output_filename
    ]
    subprocess.run(ffmpeg_cmd, check=True)
    
    # 4. Cross-publish with AI-generated titles
    publish_to_socials(output_filename, ai_generation["title"])

if __name__ == "__main__":
    main()
