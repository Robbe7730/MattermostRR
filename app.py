#!/usr/bin/env python

import mattermost

from threading import Lock
from flask import request
from flask import Flask, jsonify
app = Flask(__name__)

import configparser
import sys
import time
import random

from insults import list_of_insults

GAME_MUTEX = Lock()

# Read in the config
config = configparser.ConfigParser()
config.read('config.ini')

# Setup Mattermost connection
mm = mattermost.MMApi(config["mattermost"]["url"])
mm.login(bearer=config["mattermost"]["token"])
user = mm.get_user()

# Setup randomkick config
active_users_since = int(config["randomkick"]["active_users_since_minutes"])

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
    mm.create_post(channel, f"Goodbye @{victim['username']}")

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

@app.route("/duel", methods=["POST"])
def duel():

    # Get the channel, the user and the victim
    channel = request.form['channel_id']
    caller = request.form['user_id']
    caller_name = request.form['user_name']
    victim_name = request.form['text']

    # Verify that there is an argument (the user to pass the bomb to)
    if victim_name == '':
        return "Use /duel (otheruser) to challenge another user to a game of russian roulette"

    # Remove leading @
    if victim_name[0] == "@":
        victim_name = victim_name[1:]

    # Try to find the user
    try:
        victim = mm.get_user_by_username(victim_name)
    except mattermost.ApiException:
        return f"Could not find the user '{victim_name}'"

    # Make sure the bot is in the channel
    channel = request.form["channel_id"]
    try:
        mm.add_user_to_channel(channel, user["id"])
    except mattermost.ApiException:
        return "I do not have permission to join this channel"

    with GAME_MUTEX:
        mm.create_post(channel, f"@{caller_name} challenges @{victim['username']} for a game of russian roulette")

        # If it ducks like a quack
        players = [victim,{"username": caller_name, "id": caller}]
        game_tick = 21 # 21 zodat de caller zowel moet starten EN de verliezer is als game tick 1 is
        time.sleep(3)

        while(game_tick > 0):

            player = players[game_tick % 2]

            # 1/6 chance...
            if random.randint(0,5) == 0 or game_tick == 1:
                mm.create_post(channel, f"@{player['username']} takes the gun... **BANG**!")
                game_tick = 0
            else:
                mm.create_post(channel, f"@{player['username']} takes the gun... _click_")
                game_tick -= 1
                time.sleep(3)
                               
        mm.remove_user_from_channel(channel, player["id"])

    return "https://www.youtube.com/watch?v=h1PfrmCGFnk"   

@app.route("/stats", methods=["GET"])
def stats():
    ret = {}
    with shelve.open('russianroulette') as db:
        ret['channels_rr'] = db['channels']
        ret['totals_rr'] = db['totals']
        ret['deaths_rr'] = db['deaths']
    with shelve.open('randomkick') as db:
        ret['channels_rk'] = db['channels']
        ret['victims_rk'] = db['victims']
        ret['kickers_rk'] = db['kickers']
    return jsonify(ret)

@app.route("/insult", methods=["POST"])
def insult():

    # Get the channel, the user and the victim
    victim_name = request.form['text']

    # Verify that there is an argument (the user to pass the bomb to)
    if victim_name == '':
        return "Use /insult (name) to insult another user"

    # Remove leading @
    if victim_name[0] == "@":
        victim_name = victim_name[1:]

    # Try to find the user
    try:
        victim = mm.get_user_by_username(victim_name)
    except mattermost.ApiException:
        return f"Could not find the user '{victim_name}'"

    # Make sure the bot is in the channel
    channel = request.form["channel_id"]
    try:
        mm.add_user_to_channel(channel, user["id"])
    except mattermost.ApiException:
        return "I do not have permission to join this channel"

    message = f"@{victim_name}, {random.choice(list_of_insults)}"

    return jsonify({
            "response_type": "in_channel", 
            "text": message
    })


# Based on the mattermost library, but that has no "since" argument
def get_posts_for_channel(channel_id, since):
    data_page = mm._get("/v4/channels/"+channel_id+"/posts", params={"since":str(since)})

    for order in data_page["order"]:
        yield data_page["posts"][order]
