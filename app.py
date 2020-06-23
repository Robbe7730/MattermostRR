#!/usr/bin/env python

import mattermost

from flask import request
from flask import Flask, jsonify
app = Flask(__name__)

import configparser
import sys
import time
import random

import threading
import asyncio

# Read in the config
config = configparser.ConfigParser()
config.read('config.ini')

# Setup Mattermost connection
mm = mattermost.MMApi(config["mattermost"]["url"])
mm.login(bearer=config["mattermost"]["token"])
user = mm.get_user()

# Setup randomkick config
active_users_since = int(config["randomkick"]["active_users_since_minutes"])

# Keep track of active bombs
bombs = {}
bomb_schedule = {}

# Setup bomb config 
fuse_seconds = int(config["bomb"]["fuse_seconds"])

# # The bomb schedule worker
# def bomb_worker():
#     while True:
#         current_time = int(time.time())
#         # if current_time in bomb_schedule:
#         #     for channel_id in bomb_schedule[current_time]:
#         #         holder = bombs[channel_id]
#         #         mm.create_post(channel_id, "BOOM")
#         #         mm.remove_user_from_channel(channel_id, holder)
#         #         del bombs[channel_id]
#         #     del scheduled_bombs[current_time]
#         print(curr_time, file=sys.stderr)
#         time.sleep(1)
# 
# p = threading.Thread(target=bomb_worker)
# p.start()

# Print to stderr
def eprint(msg):
    print(msg, file=sys.stderr)

@app.route("/randomkick", methods=["POST"])
def randomkick():
    # Make sure the bot is in the channel
    channel = request.form["channel_id"]
    try:
        mm.add_user_to_channel(channel, user["id"])
    except mattermost.ApiException:
        return "I do not have permission to join this channel"

    # Get all users that have posted recently
    curr_millis = int(round(time.time() * 1000))
    delay_millis = active_users_since * 60 * 1000
    recent_posts = list(get_posts_for_channel(channel, curr_millis-delay_millis))
    recent_users = set([x["user_id"] for x in recent_posts if x["user_id"] != user["id"]])

    # Get all channel members
    channel_members = set([x["user_id"] for x in mm.get_channel_members(channel)])

    # Find the intersection
    possible_victims = channel_members & recent_users

    # Pick one
    victim = mm.get_user(random.sample(possible_victims, 1)[0])

    # Notify the channel
    mm.create_post(channel, f"Goodbye @{victim['username']}, he was randomly kicked by @{request.form['user_name']}")

    # Kick them
    mm.remove_user_from_channel(channel, victim["id"])
    return f"You just killed @{victim['username']}, do you feel happy now?"

@app.route("/russianroulette", methods=["POST"])
def russianroulette():
    # Make sure the bot is in the channel
    channel = request.form["channel_id"]
    try:
        mm.add_user_to_channel(channel, user["id"])
    except mattermost.ApiException:
        return "I do not have permission to join this channel"

    # 1/6 chance...
    if random.randint(0,6) == 4:
        message = f"BANG, @{request.form['user_name']} shot themselves."

        # Kick the user
        mm.remove_user_from_channel(channel, request.form["user_id"])
    else:
        message = "_click_"

    return jsonify({
            "response_type": "in_channel", 
            "text": message
    })

# @app.route('/bomb', methods=["POST"])
def bomb():
    # Get the channel, the user and the victim
    channel = request.form['channel_id']
    caller = request.form['user_id']
    caller_name = request.form['user_name']
    victim_name = request.form['text']

    # Make sure the bot is in the channel
    try:
        mm.add_user_to_channel(channel, user["id"])
    except mattermost.ApiException:
        return "I do not have permission to join this channel"

    # Verify that there is an argument (the user to pass the bomb to)
    if victim_name == '':
        return "Use /bomb (otheruser) to pass the bomb to another user"

    # Remove leading @
    if victim_name[0] == "@":
        victim_name = victim_name[1:]

    # Try to find the user
    try:
        victim = mm.get_user_by_username(victim_name)
    except mattermost.ApiException:
        return f"Could not find the user '{victim_name}'"

    # Make sure the victim is in the channel
    try:
        mm.add_user_to_channel(channel, victim['id'])
    except mattermost.ApiException:
        return f"I could not add @{victim_name} to this channel"


    if channel in bombs:
        # Verify that the current user has a bomb in this channel if there already is one
        if bombs[channel] != caller:
            return f"You are not holding a bomb in this channel."

        bombs[channel] = victim["id"]
        return in_channel(f"@{caller_name} gave the bomb to @{victim_name}")
    else:
        # If there is no bomb yet, create one
        bombs[channel] = victim["id"]

        # Prime it
        current_time = int(time.time())
        target_time = current_time + fuse_seconds
        if target_time not in bomb_schedule:
            bomb_schedule[target_time] = set()
        bomb_schedule[target_time].add(channel)
        eprint(bomb_schedule)

        return in_channel(f"@{caller_name} put a bomb in @{victim_name}'s hands that will blow up in {fuse_seconds} seconds! Pass it on to another user with /bomb (otheruser)")

# Based on the mattermost library, but that has no "since" argument
def get_posts_for_channel(channel_id, since):
    data_page = mm._get("/v4/channels/"+channel_id+"/posts", params={"since":str(since)})

    for order in data_page["order"]:
        yield data_page["posts"][order]

# Make a message in channel
def in_channel(message):
    return jsonify({
            "response_type": "in_channel", 
            "text": message
    })
