# syntax=docker/dockerfile:1
FROM ubuntu:22.04

# install app dependencies
RUN apt-get update && apt-get install -y python3 python3-pip && apt-get install -y python3.10-venv
RUN pip 
RUN python3 -m venv antenv
RUN . antenv/bin/activate
RUN pip install --upgrade pip
# RUN pip packages
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN apt install -y libnss3-dev libgdk-pixbuf2.0-dev libgtk-3-dev libxss-dev libasound2 libcurl4 libu2f-udev libvulkan1 xdg-utils
# Dependency for getting chrome deb file
RUN apt install -y wget 
# Install chrome dependencies
RUN apt-get install -y libappindicator1 fonts-liberation
# Fix any possible broken dependencies
RUN apt --fix-broken install
# Install chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN dpkg -i google-chrome*.deb
# Create a directory, copy over our python program, and run the CLI Interface of the program.
RUN mkdir /home/discordBot
COPY cli_interface.py /home/discordBot
COPY main.py /home/discordBot
COPY core_logic.py /home/discordBot
RUN python3 /home/discordBot/cli_interface.py
