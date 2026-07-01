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


def validate_key(name, value):
    if not value:
        raise RuntimeError(f"{name} is not set")
    # Quick sanity checks to avoid accidentally storing a URL/host inside the secret
    if "googleapis" in value or value.startswith("http"):
        raise RuntimeError(f"{name} appears malformed (contains host or URL). Please set the raw API key/token.")


validate_key("GEMINI_API_KEY", GEMINI_API_KEY)
validate_key("AGNES_API_KEY", AGNES_API_KEY)
validate_key("ELEVENLABS_API_KEY", ELEVENLABS_API_KEY)
validate_key("UPLOAD_POST_API_KEY", UPLOAD_POST_API_KEY)


def generate_ai_script_and_metadata():
    """Uses Google Gemini via AI Studio free tier to brainstorm unique content daily."""
    print("🤖 Prompting Gemini for a new script and video parameters...")

    # Build a fixed, valid endpoint using the current Gemini API.
    # Use v1 endpoint with gemini-pro model (available with free API keys)
    gemini_endpoint = "https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent"

    headers = {"Content-Type": "application/json"}
    params = None

    # Some Google "API keys" start with "AIza" and are passed as query param `key`.
    # Some tokens (OAuth-like) are passed as Bearer tokens. Support both safely here.
    if GEMINI_API_KEY.startswith("AIza"):
        params = {"key": GEMINI_API_KEY}
    else:
        headers["Authorization"] = f"Bearer {GEMINI_API_KEY}"

    prompt = (
        "You are an AI video strategist. Generate content for a 15-second sci-fi short video.\n"
        "Provide your output exactly in this format with zero extra text or pleasantries:\n"
        "TITLE: [Catchy viral title with hashtags]\n"
        "PROMPT: [Detailed text-to-video visual prompt for an image generator, under 40 words]\n"
        "SCRIPT: [A brief, cinematic 2-sentence voiceover narration under 30 words total]"
    )

    # Updated payload structure for gemini-pro:generateContent endpoint
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(gemini_endpoint, headers=headers, params=params, json=payload, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        # Print the endpoint and status for debugging but NEVER print the secret
        print(f"Gemini request failed to {gemini_endpoint}: {e}")
        raise

    # Attempt to read a text result from the response. The exact schema may vary by API/version.
    # We try several common paths to be resilient.
    resp_json = response.json()

    raw_response_text = None
    # common patterns: resp['candidates'][0]['content']['parts'][0]['text'] (Claude-like)
    try:
        raw_response_text = resp_json['candidates'][0]['content']['parts'][0]['text']
    except Exception:
        pass

    if raw_response_text is None:
        # fallback: plain text field or choices-like schema
        if isinstance(resp_json.get('output'), dict) and isinstance(resp_json['output'].get('text'), str):
            raw_response_text = resp_json['output']['text']
        elif isinstance(resp_json.get('text'), str):
            raw_response_text = resp_json['text']
        else:
            # As a last resort, stringify the whole response
            raw_response_text = str(resp_json)

    parsed_data = {}
    for line in raw_response_text.split('\n'):
        if line.startswith("TITLE:"):
            parsed_data["title"] = line.replace("TITLE:", "").strip()
        elif line.startswith("PROMPT:"):
            parsed_data["prompt"] = line.replace("PROMPT:", "").strip() + ", cinematic, vertical 9:16 format"
        elif line.startswith("SCRIPT:"):
            parsed_data["script"] = line.replace("SCRIPT:", "").strip()

    # Basic validation of parsed output
    if not parsed_data.get("prompt") or not parsed_data.get("script"):
        raise RuntimeError("Failed to parse a valid response from Gemini. Response: " + (raw_response_text[:300] + "..." if raw_response_text else ""))

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
