# Description:
# This file contains the core logic for the Reddit scraper bot.
# It uses Selenium to scrape posts from Reddit and sends the results to a Discord channel using webhooks.
# The bot can be run in the CLI or as a Discord bot.
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin
from azure.keyvault.secrets import SecretClient
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from sanitize_filename import sanitize
import logging
import sys
import asyncio
import subprocess
import requests
import re
import os
import discord
import undetected_chromedriver as uc
import asyncpraw
import aiohttp
import prawcore

# check if being ran by a docker container
if os.getenv("CHECK_ENV"):
    # Running in a CLI or local environment

    # Load environment variables from a .env file
    load_dotenv()

    # Discord token and webhook URLs from local environment variables
    # Reddit API credentials from environment variables
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
    REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
    REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    WEBHOOK = os.getenv("WEBHOOK")

else:
    # Running in a web server environment (e.g., Azure App Service, Heroku)
    
    # Set up logging
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    # Azure Key Vault URL
    vault_url = "https://FeashDiscordBot.vault.azure.net"

    # Create a secret client
    logger = logging.getLogger("azure.identity")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("[%(levelname)s %(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    credential = DefaultAzureCredential()  # ManagedIdentityCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)

    # Retrieve secrets from Azure Key Vault
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    WEBHOOK = os.getenv("WEBHOOK")
    # Reddit API credentials from environment variables
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
    REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
    REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")

# Function to sanitize the filename of the image or video scraped from Reddit
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


# Define your function to get the Reddit access token
def get_reddit_access_token():
    auth = requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
    data = {
        "grant_type": "password",
        "username": REDDIT_USERNAME,
        "password": REDDIT_PASSWORD,
    }
    headers = {"User-Agent": REDDIT_USER_AGENT}

    try:
        response = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data=data,
            headers=headers,
        )
        response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)

        token = response.json().get("access_token")
        if not token:
            raise KeyError("Access token not found in response.")

        return token

    except requests.exceptions.RequestException as err:
        print(f"Request error occurred: {err}")
        raise  # Re-raise the exception to handle it higher up
    except KeyError as key_err:
        print(f"KeyError: {key_err}")
        raise  # Re-raise the exception to handle it higher up

# Get the Reddit access token
REDDIT_ACCESS_TOKEN = get_reddit_access_token()

# Set up the headers for authenticated API requests, including the header for NSFW content
headers = {
    "Authorization": f"bearer {REDDIT_ACCESS_TOKEN}",
    "User-Agent": REDDIT_USER_AGENT,
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}

class ScraperBot:
    post_urls = {}  # Dictionary to store post URLs

    def __init__(self):

        # Set up the Discord bot with specific intents
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.bot)

        # IMPORTANT: Change the subreddits to scrape here to whatever you want
        self.subreddits = {
            1: "memes",
            2: "combatfootage",
            3: "greentext",
            4: "dankmemes",
            5: "pics",
        }

        self.setup_bot_commands()

    def setup_bot_commands(self):

        @app_commands.describe(
            subreddit_number="The number of the subreddit to scrape",
            num_posts="The number of posts to scrape (default: 1)",
        )

        # Define the scrape command
        @self.tree.command(name="scrape", description="Scrape posts from a subreddit")
        async def scrape_command(
            interaction: discord.Interaction, subreddit_number: int, num_posts: int = 1
        ):
            if subreddit_number in self.subreddits:
                subreddit_url = self.subreddits[subreddit_number]

                await interaction.response.defer()

                await interaction.followup.send(
                    f"Starting to scrape {num_posts} posts from: {subreddit_url}"
                )

                await self.scrape_subreddit(interaction, subreddit_url, num_posts)

            else:
                await interaction.response.send_message(
                    "Invalid subreddit number. Please choose a number between 1 and 5."
                )

        # Define the list_subreddits command
        @self.tree.command(
            name="list_subreddits", description="List available subreddits"
        )
        async def list_subreddits(interaction: discord.Interaction):
            try:
                subreddit_list = "\n".join(
                    [f"{k}. {v}" for k, v in self.subreddits.items()]
                )
                await interaction.response.send_message(
                    f"Available subreddits to scrape:\n{subreddit_list}"
                )
            except Exception as e:
                print(f"Error listing subreddits: {e}")
                await interaction.response.send_message("Error listing subreddits.")

            # Define the scrape_custom command

        @self.tree.command(
            name="scrape_custom", description="Scrape posts from a custom subreddit"
        )
        async def scrape_custom_command(
            interaction: discord.Interaction, subreddit_name: str, num_posts: int = 1
        ):
            try:
                subreddit = await self.check_subreddit_exists(subreddit_name)
                if subreddit:
                    await interaction.response.defer()
                    await interaction.followup.send(
                        f"Starting to scrape {num_posts} posts from: r/{subreddit_name}"
                    )
                    await self.scrape_subreddit(interaction, subreddit_name, num_posts)
                else:
                    await interaction.response.send_message(
                        "Invalid subreddit name. Community not found. Please provide a valid subreddit name."
                    )

            except Exception as e:
                await interaction.response.send_message(
                    f"An error occurred while processing the command: {str(e)}"
                )


    def handle_error_message(self, error_message):
        if "community not found" in error_message.lower():
            return False  # Subreddit does not exist
        elif "is private" in error_message.lower():
            return False  # Subreddit is private
        elif "is banned" in error_message.lower():
            return False  # Subreddit is banned
        else:
            return True  # Subreddit exists
        
    async def check_subreddit_exists(self, subreddit_name):
        try:
            response = requests.get(
                f"https://oauth.reddit.com/r/{subreddit_name}/about", headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("error"):
                    error_message = data["message"]
                    subreddit_exists = self.handle_error_message(error_message)
                else:
                    subreddit_exists = True  # Subreddit exists
            elif response.status_code == 404:
                subreddit_exists = False  # Subreddit not found
            else:
                # Handle other response status codes as needed
                print(f"Unexpected status code: {response.status_code}")
                subreddit_exists = None
        
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            subreddit_exists = None
        except Exception as e:
            print(f"Unexpected error occurred: {e}")
            subreddit_exists = None
        
        return subreddit_exists

    async def scrape_subreddit(self, interaction, subreddit_url, num_posts):
        print(f"Scraping {num_posts} posts from: {subreddit_url}")

        try:
            response = requests.get(
                f"https://oauth.reddit.com/r/{subreddit_url}/top?limit={num_posts}",
                headers=headers,
            )
            response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)

            if response.status_code == 200:
                posts = response.json().get("data", {}).get("children", [])
                for post in posts:
                    post_data = post.get("data", {})
                    if post_data:
                        print("Post data:", post_data)
                        print("Moving to get_post_content")
                        await self.get_post_content(post_data, interaction)
            else:
                await interaction.followup.send(f"Failed to fetch posts. Status code: {response.status_code}")

        except requests.exceptions.HTTPError as http_err:
            await interaction.followup.send(f"HTTP error occurred: {http_err}")
            print(f"HTTP error occurred: {http_err}")
        except requests.exceptions.RequestException as e:
            await interaction.followup.send(f"An error occurred: {e}")
            print(f"An error occurred: {e}")
        except Exception as e:
            print("Error encountered in scrape_subreddit:", e)
            await interaction.followup.send(f"An unexpected error occurred: {e}")

    # Get the content of a specific post
    async def get_post_content(self, post, interaction=None):
        try:
            print("Getting post content for", post.get("url"))
            title = post.get("title")
            nsfw = post.get("over_18", False)  # Check if the post is NSFW
            gallery = post.get("is_gallery", False)

            if gallery:
                await self.process_gallery(post, title, interaction, nsfw)
            else:
                media = post.get("media")
                video = media["reddit_video"]["fallback_url"] if media and "reddit_video" in media else None
                hls_video = media["reddit_video"]["hls_url"] if media and "reddit_video" in media else None
                image = post.get("url") if post.get("url").endswith((".jpg", ".jpeg", ".png")) else None
                gif = post.get("url") if post.get("url").endswith(".gif") else None

                if hls_video:
                    await self.process_video(hls_video, title, interaction, nsfw)
                elif video and not image and not gif:
                    await self.process_video(video, title, interaction, nsfw)
                elif image and not video and not gif:
                    await self.process_image(image, title, interaction, nsfw)
                elif gif and not image and not video:
                    await self.process_gif(gif, title, interaction, nsfw)
                else:
                    print("No image, video, gif, or gallery found.")
                    await interaction.followup.send(f"No image, video, gif, or gallery found for post: {title} ({post.get('url')})")

        except Exception as e:
            print("Error getting post content:", e)
            await interaction.followup.send(f"An unexpected error occurred while processing the post: {e}")

    async def process_gallery(self, post, title, interaction, nsfw):
        try:
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
                        await self.process_image(url, title, interaction, nsfw)
                    elif mime_type.startswith("video"):
                        await self.process_video(url, title, interaction, nsfw)
                    elif mime_type.endswith("gif"):
                        await self.process_gif(url, title, interaction, nsfw)
                    else:
                        print(f"Unknown media type for {media_id}")

        except Exception as e:
            print("Error processing gallery content:", e)
            await interaction.followup.send(f"An unexpected error occurred while processing the gallery: {e}")

    # Process the image and send it to the Discord channel
    async def process_image(self, image_url, title, interaction=None, nsfw=False):
        print("Image URL:", image_url)

        image_filename = sanitize_filename(f"{title}.png")

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                content = await response.read()

        with open(image_filename, "wb") as file:
            file.write(content)

        title_payload = {"content": f"{title}\n{image_url}"}
        files = {"file": open(image_filename, "rb")}

        await self.send_to_discord_channel(title_payload, files, interaction)

        files["file"].close()
        os.remove(image_filename)

    # Process the video and send it to the Discord channel
    async def process_video(self, video_url, title, interaction=None, nsfw=False):
        print("Video URL:", video_url)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=None) as response:
                content_type = response.headers.get('Content-Type')
                
                if (
                    "application/vnd.apple.mpegurl" in content_type
                    or "application/x-mpegurl" in content_type
                ):
                    # HLS stream detected, use FFmpeg to convert
                    video_filename = sanitize_filename(f"{title}.mp4")
                    
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-i", video_url,
                        "-c:v", "libx264",  # Video codec
                        "-crf", "25",  # Constant Rate Factor (0-51, lower is better quality)
                        "-preset", "veryfast",  # Preset for encoding speed vs. compression ratio
                        "-max_muxing_queue_size", "1024",  # Max demux queue size
                        "-c:a", "aac",  # Audio codec
                        "-b:a", "128k",  # Audio bitrate
                        "-bsf:a", "aac_adtstoasc",
                        video_filename,
                    ]
                    
                    try:
                        subprocess.run(ffmpeg_cmd, check=True, timeout=300)  # 5-minute timeout
                        print(f"Successfully downloaded and processed video: {video_filename}")
                        
                        # Check file size
                        file_size = os.path.getsize(video_filename)
                        if file_size == 0:
                            print("Downloaded video file is empty")
                            return
                        elif file_size > 25 * 1024 * 1024:
                            print("Downloaded video file is too large to send to Discord")
                            title_payload = {"content": f"{title}\n{video_url}"}
                            await self.send_to_discord_channel(title_payload, files=None, interaction=interaction)
                            return
                        
                        # Send video to Discord
                        title_payload = {"content": f"{title}\n{video_url}"}
                        if nsfw:
                            title_payload["content"] = f"NSFW: {title}\n{video_url}"
                        files = {"file": open(video_filename, "rb")}
                        
                        await self.send_to_discord_channel(title_payload, files, interaction)
                        
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
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > 25 * 1024 * 1024:  # 25MB limit
                        print(f"Video at {video_url} is larger than 25MB, skipping processing.")
                        title_payload = {"content": f"{title}\n{video_url}"}
                        await self.send_to_discord_channel(title_payload, files=None, interaction=interaction)
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

                    await self.send_to_discord_channel(title_payload, files, interaction)

                    files["file"].close()
                    os.remove(video_filename)

    # Process the gif and send it to the Discord channel
    async def process_gif(self, gif_url, title, interaction=None, nsfw=False):
        print("Gif URL:", gif_url)
        async with aiohttp.ClientSession() as session:
            async with session.get(gif_url) as response:
                content = await response.read()

        gif_filename = sanitize_filename(f"{title}.gif")

        with open(gif_filename, "wb") as file:
            file.write(content)

        title_payload = {"content": f"{title}\n{gif_url}"}
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
                    if key == "file" and not title_payload["content"].endswith((".jpg", ".jpeg", ".png")):
                        await text_channel.send(file=discord.File(value))
                    files[key].close()

        return

    # Get the subreddit from the user in the CLI
    def getSubredditCLI(self):
        print("Which subreddit would you like to scrape?")
        for key, value in self.subreddits.items():
            print(f"{key}. {value}")
        while True:
            subreddit = int(
                input("Enter the number of the subreddit you would like to scrape: ")
            )
            if subreddit in self.subreddits:
                return self.subreddits[subreddit]
            else:
                print("Invalid input. Please enter a valid choice.")

    # Select the number of posts to scrape from the subreddit
    async def select_posts(self, subreddit_name, num_posts):
        try:
            reddit = asyncpraw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent=REDDIT_USER_AGENT,
            )
            subreddit = await reddit.subreddit(subreddit_name)
            top_posts = subreddit.top(limit=num_posts)
            return top_posts
        except prawcore.exceptions.Redirect:
            print("Invalid subreddit name. Please provide a valid subreddit name.")
            return None

    # Run the CLI interface
    def run_cli(self):
        subreddit_name = self.getSubredditCLI()
        num_posts = int(input("How many posts would you like to scrape? "))

        # Define an async function to run the CLI
        async def cli_helper():
            top_posts = await self.select_posts(subreddit_name, num_posts)
            if not top_posts:
                print(f"No posts found for subreddit: {subreddit_name}")
                return
            for post in top_posts:
                await self.get_post_content(post)

        # Get the existing event loop or create a new one if none exists
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(cli_helper())
                new_loop.close()
            else:
                loop.run_until_complete(cli_helper())
        except Exception as e:
            print(f"An error occurred: {e}")

    # async commands
    async def sync_commands(self):
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    # Run the Discord bot
    def run_discord(self):
        # Define the on_ready event
        @self.bot.event
        async def on_ready():
            await self.sync_commands()
            print(f"{self.bot.user} has connected to Discord!")
            print(f"Bot is active in {len(self.bot.guilds)} servers.")
            print("Ready to receive commands!")

            # Send a call to the webhook that the bot is ready
            try:
                webhook_message = {
                    "content": f"{self.bot.user} is ready to receive commands!"
                }
                requests.post(WEBHOOK, json=webhook_message)
            except Exception as e:
                print(f"Failed to send webhook message: {e}")

        self.bot.run(DISCORD_TOKEN)
