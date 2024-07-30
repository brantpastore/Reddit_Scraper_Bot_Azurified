import requests
import aiohttp
import os
import subprocess
import re
import discord
from urllib.parse import urljoin, urlparse
from utils import sanitize_filename


class WebScraper:
    def __init__(self, headers):
        self.headers = headers

    async def scrape_subreddit(
        self, interaction, subreddit_url, num_posts, filter_type, time_range
    ):
        print(f"Scraping {num_posts} posts from: {subreddit_url}")

        # Default to hot if filter type is not provided, or if it's invalid
        try:
            if filter_type in ["top", "controversial"]:
                response = requests.get(
                    f"https://oauth.reddit.com/r/{subreddit_url}/{filter_type}?limit={num_posts}&t={time_range}",
                    headers=self.headers,
            )
            elif filter_type in ["hot", "new", "rising"]:
                response = requests.get(
                    f"https://oauth.reddit.com/r/{subreddit_url}/{filter_type}?limit={num_posts}",
                    headers=self.headers,
            )
            else:
                response = requests.get(
                    f"https://oauth.reddit.com/r/{subreddit_url}/hot?limit={num_posts}",
                    headers=self.headers,
            )
            
            response.raise_for_status()

            if response.status_code == 200:
                posts = response.json().get("data", {}).get("children", [])
                for post in posts:
                    post_data = post.get("data", {})
                    if post_data:
                        print("Post data:", post_data)
                        print("Moving to get_post_content")
                        await self.get_post_content(post_data, interaction)
            else:
                await interaction.followup.send(
                    f"Failed to fetch posts. Status code: {response.status_code}"
                )

        except requests.exceptions.HTTPError as http_err:
            await interaction.followup.send(f"HTTP error occurred: {http_err}")
            print(f"HTTP error occurred: {http_err}")
        except requests.exceptions.RequestException as e:
            await interaction.followup.send(f"An error occurred: {e}")
            print(f"An error occurred: {e}")
        except Exception as e:
            print("Error encountered in scrape_subreddit:", e)
            await interaction.followup.send(f"An unexpected error occurred: {e}")

    async def get_post_content(self, post, interaction=None):
        try:
            print("Getting post content for", post.get("url"))
            title = post.get("title")
            nsfw = post.get("over_18", False)
            gallery = post.get("is_gallery", False)
            perm_url = post.get("permalink")
            reddit_post_url = urljoin("https://www.reddit.com", perm_url)

            if gallery:
                await self.process_gallery(post, title, interaction, nsfw)
            else:
                media = post.get("media")
                video = (
                    media["reddit_video"]["fallback_url"]
                    if media and "reddit_video" in media
                    else None
                )
                hls_video = (
                    media["reddit_video"]["hls_url"]
                    if media and "reddit_video" in media
                    else None
                )
                image = (
                    post.get("url")
                    if post.get("url").endswith((".jpg", ".jpeg", ".png"))
                    else None
                )
                gif = post.get("url") if post.get("url").endswith(".gif") else None

                if hls_video:
                    backup_video = video if video else None
                    await self.process_video(
                        hls_video, title, backup_video, interaction, nsfw
                    )
                elif video and not image and not gif:
                    await self.process_video(video, title, interaction, nsfw)
                elif image and not video and not gif:
                    await self.process_image(
                        image, title, reddit_post_url, interaction, nsfw
                    )
                elif gif and not image and not video:
                    await self.process_gif(
                        gif, title, reddit_post_url, interaction, nsfw
                    )
                else:
                    print("No image, video, gif, or gallery found.")
                    await interaction.followup.send(
                        f"No image, video, gif, or gallery found for post: {title} ({post.get('url')})"
                    )

        except Exception as e:
            print("Error getting post content:", e)
            await interaction.followup.send(
                f"An unexpected error occurred while processing the post: {e}"
            )

    async def process_gallery(self, post, title, interaction, nsfw):
        try:
            print(f"Interaction type: {type(interaction)}, Interaction: {interaction}")

            if not hasattr(interaction, "followup"):
                raise ValueError(
                    "The interaction object does not have the expected 'followup' attribute."
                )

            gallery_data = post.get("gallery_data", {}).get("items", [])
            media_metadata = post.get("media_metadata", {})

            # Process only the first item in the gallery
            if gallery_data:
                item = gallery_data[0]
                media_id = item.get("media_id")
                if media_id:
                    media_info = media_metadata.get(media_id, {})
                    mime_type = media_info.get("m", "")
                    url = f"https://i.redd.it/{media_id}.jpg"

                    if mime_type.startswith("image"):
                        await self.process_image(
                            url, title, post["url"], interaction, nsfw
                        )
                    elif mime_type.startswith("video"):
                        await self.process_video(
                            url, title, post["url"], interaction, nsfw
                        )
                    elif mime_type.endswith("gif"):
                        await self.process_gif(
                            url, title, post["url"], interaction, nsfw
                        )
                    else:
                        print(f"Unknown media type for {media_id}")

        except Exception as e:
            print("Error processing gallery content:", e)
            await interaction.followup.send(
                f"An unexpected error occurred while processing the gallery: {e}"
            )

    # Process the image and send it to the Discord channel
    async def process_image(
        self, image_url, title, reddit_post_url=None, interaction=None, nsfw=False
    ):
        print("Image URL:", image_url)

        image_filename = sanitize_filename(f"{title}.jpg")

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                content = await response.read()

        with open(image_filename, "wb") as file:
            file.write(content)

        title_payload = {"content": f"{title}\n<{reddit_post_url}>"}
        files = {"file": open(image_filename, "rb")}

        try:
            await self.send_to_discord_channel(title_payload, files, interaction)
        finally:
            files["file"].close()
            os.remove(image_filename)

    # Process the video and send it to the Discord channel
    async def process_video(
        self, video_url, title, backup_video=None, interaction=None, nsfw=False
    ):
        print("Video URL:", video_url)

        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=None) as response:
                content_type = response.headers.get("Content-Type")

                if (
                    "application/vnd.apple.mpegurl" in content_type
                    or "application/x-mpegurl" in content_type
                ):
                    # HLS stream detected, use FFmpeg to convert
                    video_filename = sanitize_filename(f"{title}.mp4")

                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-i",
                        video_url,
                        "-c:v",
                        "libx264",  # Video codec
                        "-crf",
                        "25",  # Constant Rate Factor (0-51, lower is better quality)
                        "-preset",
                        "veryfast",  # Preset for encoding speed vs. compression ratio
                        "-max_muxing_queue_size",
                        "1024",  # Max demux queue size
                        "-c:a",
                        "aac",  # Audio codec
                        "-b:a",
                        "128k",  # Audio bitrate
                        "-bsf:a",
                        "aac_adtstoasc",
                        video_filename,
                    ]

                    try:
                        subprocess.run(
                            ffmpeg_cmd, check=True, timeout=300
                        )  # 5-minute timeout
                        print(
                            f"Successfully downloaded and processed video: {video_filename}"
                        )

                        # Check file size
                        file_size = os.path.getsize(video_filename)
                        if file_size == 0:
                            print("Downloaded video file is empty")
                            return
                        elif file_size > 25 * 1024 * 1024:
                            print(
                                "Downloaded video file is too large to send to Discord"
                            )
                            title_payload = {"content": f"{title}\n{backup_video}"}
                            await self.send_to_discord_channel(
                                title_payload, files=None, interaction=interaction
                            )
                            return

                        # Send video to Discord

                        # Regular expression to remove the /DASH and everything after it
                        trimmed_video_url = re.sub(r"/DASH.*", "", backup_video)

                        title_payload = {"content": f"{title}\n<{trimmed_video_url}>"}
                        if nsfw:
                            title_payload["content"] = (
                                f"NSFW: {title}\n{trimmed_video_url}"
                            )
                        files = {"file": open(video_filename, "rb")}

                        await self.send_to_discord_channel(
                            title_payload, files, interaction
                        )

                        files["file"].close()
                        os.remove(video_filename)

                    except subprocess.TimeoutExpired:
                        print("FFmpeg process timed out")
                        return
                    except subprocess.CalledProcessError as e:
                        print(f"Error processing video: {e}")
                        return

                else:
                    # Regular video file, handle as before
                    content_length = response.headers.get("Content-Length")
                    if (
                        content_length and int(content_length) > 25 * 1024 * 1024
                    ):  # 25MB limit
                        print(
                            f"Video at {video_url} is larger than 25MB, skipping processing."
                        )
                        title_payload = {"content": f"{title}\n{video_url}"}
                        await self.send_to_discord_channel(
                            title_payload, files=None, interaction=interaction
                        )
                        return

                    extension = os.path.splitext(urlparse(video_url).path)[1] or ".mp4"
                    video_filename = sanitize_filename(f"{title}{extension}")

                    with open(video_filename, "wb") as video_file:
                        while True:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            video_file.write(chunk)

                    # Send video to Discord
                    title_payload = {"content": f"{title}\n{video_url}"}
                    if nsfw:
                        title_payload["content"] = f"NSFW: {title}\n{video_url}"
                    files = {"file": open(video_filename, "rb")}

                    await self.send_to_discord_channel(
                        title_payload, files, interaction
                    )

                    files["file"].close()
                    os.remove(video_filename)

    # Process the gif and send it to the Discord channel
    async def process_gif(
        self, gif_url, title, reddit_post_url=None, interaction=None, nsfw=False
    ):
        print("Gif URL:", gif_url)
        async with aiohttp.ClientSession() as session:
            async with session.get(gif_url) as response:
                content = await response.read()

        gif_filename = sanitize_filename(f"{title}.gif")

        with open(gif_filename, "wb") as file:
            file.write(content)

        title_payload = {"content": f"{title}\n<{reddit_post_url}>"}
        files = {"file": open(gif_filename, "rb")}

        await self.send_to_discord_channel(title_payload, files, interaction)

        files["file"].close()
        os.remove(gif_filename)

    async def send_to_discord_channel(self, title_payload, files, interaction):
        # check the channel the command was called from,
        # and send the message to that channel
        text_channel = interaction.channel

        print(f"Sending message to channel: {text_channel}")

        # send the message with the title payload
        await text_channel.send(content=title_payload["content"])

        # send the files if there are any
        if files:
            for key, value in files.items():
                if value:
                    if key == "file" and not title_payload["content"].endswith(
                        (".jpg", ".jpeg", ".png")
                    ):
                        await text_channel.send(file=discord.File(value))
                    files[key].close()

        return
