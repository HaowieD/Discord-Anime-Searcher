import discord
import requests
import io
import re
import aiohttp
from moviepy.editor import VideoFileClip
import tempfile
import os

DISCORD_TOKEN = 'token'
SAUCENAO_API_KEY = 'api'
ALLOWED_CHANNEL_ID = "channel ID"  # channel bot writes

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

def clean_anime_name(name: str) -> str:
    return re.sub(r'\.mp4$', '', name, flags=re.IGNORECASE)

async def fetch_trace_moe(image_bytes):
    response = requests.post(
        'https://api.trace.moe/search',
        files={'image': ('image.jpg', image_bytes)}
    )
    data = response.json()
    if not data.get('result'):
        return {}

    result = data['result'][0]
    anime_name = result.get('anime') or result.get('filename', 'Unknown')
    anime_name = clean_anime_name(anime_name)

    return {
        "anime": anime_name,
        "episode": result.get('episode', '?'),
        "similarity": f"{result.get('similarity', 0)*100:.2f}%",
        "video": result.get('video', None)
    }

async def fetch_saucenao(image_bytes):
    response = requests.post(
        f'https://saucenao.com/search.php?output_type=2&api_key={SAUCENAO_API_KEY}',
        files={'file': ('image.jpg', image_bytes)}
    )
    data = response.json()
    if not data.get('results'):
        return {}

    result = data['results'][0]
    data_fields = result.get('data', {})

    title = data_fields.get('title') or data_fields.get('eng_name') or data_fields.get('jp_name') or 'Unknown'

    ext_urls = data_fields.get('ext_urls', [])
    mal_url = None
    anilist_url = None

    if 'mal_id' in data_fields:
        mal_url = f"https://myanimelist.net/anime/{data_fields['mal_id']}"
    else:
        for url in ext_urls:
            if "myanimelist.net" in url:
                mal_url = url
                break

    for url in ext_urls:
        if "anilist.co" in url:
            anilist_url = url
            break

    return {
        "title": title,
        "similarity": result.get('header', {}).get('similarity', '?'),
        "link": ext_urls[0] if ext_urls else 'No link found',
        "mal_url": mal_url,
        "anilist_url": anilist_url
    }

async def download_video_as_gif(video_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(video_url) as resp:
            if resp.status != 200:
                return None
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_vid:
                temp_vid.write(await resp.read())
                temp_vid_path = temp_vid.name

    gif_path = temp_vid_path.replace(".mp4", ".gif")

    try:
        clip = VideoFileClip(temp_vid_path).subclip(0, 10).resize(height=300)
        clip.write_gif(gif_path, program='ffmpeg')
        clip.close()  

        with open(gif_path, 'rb') as gif_file:
            gif_bytes = gif_file.read()

        return gif_bytes
    finally:
        try:
            os.remove(temp_vid_path)
        except PermissionError:
            print(f"⚠ Could not delete {temp_vid_path} (file still in use).")

        if os.path.exists(gif_path):
            os.remove(gif_path)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != ALLOWED_CHANNEL_ID:
        return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and 'image' in attachment.content_type:
                image_bytes = await attachment.read()

                trace_data = await fetch_trace_moe(image_bytes)
                sauce_data = await fetch_saucenao(image_bytes)

                sauce_title = sauce_data.get('title', 'Unknown')
                if sauce_title.lower() == 'unknown' and trace_data and trace_data.get('anime'):
                    sauce_title = trace_data['anime']

                embed = discord.Embed(
                    title="Anime Search Results",
                    color=0x8e44ad
                )

                embed.set_thumbnail(url="attachment://image.jpg")

                if trace_data:
                    video_url = trace_data.get('video')
                    embed.add_field(
                        name="trace.moe",
                        value=(
                            f"**Anime:** {trace_data['anime']}\n"
                            f"**Episode:** {trace_data['episode']}\n"
                            f"**Similarity:** {trace_data['similarity']}\n"
                            f"**Video:** [Click here]({video_url})" if video_url else "**Video:** Not available"
                        ),
                        inline=False
                    )

                if sauce_data:
                    mal_field = f"[MyAnimeList]({sauce_data['mal_url']})" if sauce_data.get('mal_url') else "No MAL link"
                    anilist_field = f"[AniList]({sauce_data['anilist_url']})" if sauce_data.get('anilist_url') else "No AniList link"

                    embed.add_field(
                        name="SauceNAO",
                        value=(
                            f"**Title:** {sauce_title}\n"
                            f"**Similarity:** {sauce_data['similarity']}%\n"
                            f"**AniDB/Other:** [Click here]({sauce_data['link']})\n"
                            f"{mal_field} | {anilist_field}"
                        ),
                        inline=False
                    )

                files = [discord.File(io.BytesIO(image_bytes), filename="image.jpg")]

                # if there's vid available add gif to embedd
                gif_bytes = None
                if trace_data.get('video'):
                    gif_bytes = await download_video_as_gif(trace_data['video'])
                    if gif_bytes:
                        files.append(discord.File(io.BytesIO(gif_bytes), filename="preview.gif"))
                        embed.set_image(url="attachment://preview.gif")

                await message.channel.send(files=files, embed=embed)

client.run(DISCORD_TOKEN)
