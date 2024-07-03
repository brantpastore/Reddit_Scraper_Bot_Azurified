# Description:
# This file contains the core logic for the Reddit scraper bot.
# It uses Selenium to scrape posts from Reddit and sends the results to a Discord channel using webhooks.
# The bot can be run in the CLI or as a Discord bot.
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from discord import app_commands
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin
import time
import requests
import re
import os
import discord
import logging
import m3u8
import subprocess
import tempfile
import ffmpeg


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Discord token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Webhook URLs
test_memes_webhook = "https://discord.com/api/webhooks/1257428323525591162/5524Jri5RRLfaU8y7XBr1cLl5zqHLvO_XaHF9pU7FaY0gvw0LB-00a3JzmBsq2jqKBwF"
production_memes_webhook = "https://discord.com/api/webhooks/1256729712558997636/3kJ-pRBISUkorNMiDKFlG3sDO0K6aOfc-iFzjtPGH3HpIChZOeCUE4B-sh9oJgwao74I"
warfootage_webhook = "https://discord.com/api/webhooks/1256729251126968441/O4EjarVM_VK2c1QpfBzE6h74Fxuv0AD8trapwrAKcUzSlYbPxZROvPXDfYW8eFlphdn3"


# Function to sanitize the filename of the image or video scraped from Reddit
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


class ScraperBot:
    post_urls = {}  # Dictionary to store post URLs

    def __init__(self):
        # set up selenium options for headless browsing
        options = Options()
        options.add_argument("--headless")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)

        # Set up the Discord bot with specific intents
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.bot)

        # IMPORTANT: Change the subreddits to scrape here to whatever you want
        self.subreddits = {
            1: "https://www.reddit.com/r/memes/top/",
            2: "https://www.reddit.com/r/combatfootage/top/",
            3: "https://www.reddit.com/r/greentext/top/",
            4: "https://www.reddit.com/r/dankmemes/top/",
            5: "https://www.reddit.com/r/pics/top/",
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
                await interaction.response.send_message(
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
            subreddit_list = "\n".join(
                [f"{k}. {v.split('/')[4]}" for k, v in self.subreddits.items()]
            )
            await interaction.response.send_message(
                f"Available subreddits to scrape:\n{subreddit_list}"
            )

        # Define the hello command for test purposes
        @self.bot.event
        async def on_message(message):
            if message.content.startswith("/hello"):
                await message.channel.send(
                    "Hello!, I am a bot that scrapes posts from Reddit."
                )

    # Scrapes a subreddit and sends the results to the Discord channel
    async def scrape_subreddit(self, interaction, subreddit_url, num_posts):
        self.get_top_posts(subreddit_url, num_posts)
        await interaction.followup.send(
            f"Finished scraping {num_posts} posts from {subreddit_url}"
        )

    # Function to get the subreddit from the user in the CLI
    def getSubredditCLI(self):
        print("Which subreddit would you like to scrape?")
        for key, value in self.subreddits.items():
            print(f"{key}. {value.split('/')[4]}")
        while True:
            subreddit = int(
                input("Enter the number of the subreddit you would like to scrape: ")
            )
            if subreddit in self.subreddits:
                return self.subreddits[subreddit]
            else:
                print("Invalid input. Please enter a valid choice.")

    # Navigate to the subreddit URL
    def go_to_subreddit(self, subreddit):
        self.driver.get(subreddit)
        time.sleep(3)

    # Scroll down the page to load more posts
    def scroll_down(self):
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    # Select the number of posts to scrape from the subreddit
    def select_posts(self, num_posts):

        posts = []  # List to store post URLs

        while (
            len(posts) < num_posts
        ):  # Keep scrolling until we have the desired number of posts

            article_elements = self.driver.find_elements(By.TAG_NAME, "article")
            print(f"Found {len(article_elements)} articles so far.")

            for post in article_elements:

                if len(posts) >= num_posts:  # If we have enough posts,
                    break
                try:  # else, try to find the post link
                    link = post.find_element(By.CSS_SELECTOR, 'a[href^="/r/"]')
                    post_url = link.get_attribute("href")
                    if (
                        post_url not in posts
                    ):  # If the post is not already in the list, add it
                        posts.append(post_url)
                        print(f"Post {len(posts)}: {post_url}")
                except Exception as e:
                    print(f"Error finding post link: {e}")

            if (
                len(posts) < num_posts
            ):  # If we still don't have enough posts, scroll down
                self.scroll_down()

        return posts

    # Get the top posts from the subreddit
    def get_top_posts(self, subreddit, num_posts=1):

        self.go_to_subreddit(subreddit)

        post_urls = self.select_posts(num_posts)

        for i, url in enumerate(post_urls):  # Loop through the post URLs
            self.post_urls[i] = url
            self.get_post_content(url)

    # Get the content of a specific post
    def get_post_content(self, post_url):
        print("Getting post content for", post_url)
        self.driver.get(post_url)

        try:
            title = self.driver.find_element(By.CSS_SELECTOR, "h1").text
            # sanitize the title, remove all non-alphanumeric characters, but keep spaces
            title = re.sub(r"[^a-zA-Z0-9 ]", "", title)
        except Exception as e:
            print(f"Error finding title: {e}")
            title = "No title found"

        print("Title:", title)

        image = None  # Initialize image variable
        try:  # Try to find the image
            image = self.driver.find_element(
                By.CSS_SELECTOR, 'img[alt^="r/"]'
            ).get_attribute("src")
        except:
            print("No image found.")

        video = None  # Initialize video variable
        try:  # Try to find the video
            video = self.driver.find_element(
                By.CSS_SELECTOR, "shreddit-player"
            ).get_attribute("src")
        except:
            print("No video found.")

        if image and not video:  # If we found an image but no video, process the image
            self.process_image(image, title)
        elif video and not image:  # If we found a video but no image, process the video
            self.process_video(video, title)
        else:
            print("No image or video found.")

    # Process the image and send it to the Discord channel
    def process_image(self, image_url, title):
        print("Image URL:", image_url)
        self.driver.get(image_url)
        image_filename = sanitize_filename(f"{title}.png")
        self.driver.save_screenshot(image_filename)

        title_payload = {"content": title}
        files = {"file": open(image_filename, "rb")}
        requests.post(warfootage_webhook, files=files, data=title_payload)
        files["file"].close()
        os.remove(image_filename)

    def process_video(self, video_url, title):
        print("Video URL:", video_url)
        video_response = requests.get(video_url, stream=True)

        # Determine if the content is a BLOB
        content_type = video_response.headers.get("Content-Type")
        if (
            "application/vnd.apple.mpegurl" in content_type
            or "application/x-mpegurl" in content_type
        ):
            # Handle M3U8 playlist
            video_filename = sanitize_filename(f"{title}.mp4")

            ffmpeg_cmd = [
                "ffmpeg",
                "-i",
                video_url,
                "-c:v",
                "libx264",  # Video codec
                "-crf",
                "45",  # Constant Rate Factor (0-51, lower is better quality)
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
                subprocess.run(ffmpeg_cmd, check=True, timeout=300)  # 5-minute timeout
                logger.info(
                    f"Successfully downloaded and processed video: {video_filename}"
                )

                # check file size
                file_size = os.path.getsize(video_filename)
                if file_size == 0:
                    logger.error("Downloaded video file is empty")
                    return
                # else if file size is greater than 25mb, it cannot be sent to discord
                elif file_size > 25 * 1024 * 1024:
                    logger.error(
                        "Downloaded video file is too large to send to Discord"
                    )
                    # post to discord the title, and the url of the video
                    title_payload = {"content": title}
                    requests.post(warfootage_webhook, data=title_payload)
                    return

            except subprocess.TimeoutExpired:
                logger.error("FFmpeg process timed out")
                return
            except subprocess.CalledProcessError as e:
                logger.error(f"Error processing video: {e}")
                return

        else:
            # Handle direct video download
            extension = os.path.splitext(urlparse(video_url).path)[1] or ".mp4"
            video_filename = sanitize_filename(f"{title}{extension}")

            with open(video_filename, "wb") as video_file:
                for chunk in video_response.iter_content(chunk_size=1024):
                    video_file.write(chunk)

        # Send video to Discord or further processing
        title_payload = {"content": title}
        files = {"file": open(video_filename, "rb")}
        requests.post(warfootage_webhook, files=files, data=title_payload)
        files["file"].close()
        os.remove(video_filename)

    # Run the CLI interface
    def run_cli(self):
        subreddit = self.getSubredditCLI()
        num_posts = int(input("How many posts would you like to scrape? "))
        self.get_top_posts(subreddit, num_posts)

    # Run the Discord bot
    def run_discord(self):
        @self.bot.event
        async def on_ready():
            try:  # Try to sync the commands
                synced = await self.tree.sync()
                print(f"Synced {len(synced)} command(s)")
            except Exception as e:
                print(f"Failed to sync commands: {e}")
            print(f"{self.bot.user} has connected to Discord!")
            print(f"Bot is active in {len(self.bot.guilds)} servers.")
            print("Ready to receive commands!")

        self.bot.run(DISCORD_TOKEN)
