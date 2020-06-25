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
import shelve

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

# Setup duel config
max_duel_game_tick = int(config["duel"]["max_game_tick"])

# Setup shelve storage
with shelve.open('stats') as db:
    if 'russianroulette' not in db:
        db['russianroulette'] = []
    if 'randomkick' not in db:
        db['randomkick'] = []
    if 'duel' not in db:
        db['duel'] = []
    if 'insult' not in db:
        db['insult'] = []

def eprint(msg):
    print(msg, file=sys.stderr)

@app.route("/randomkick", methods=["POST"])
def randomkick():
    # Make sure the bot is in the channel
    channel = request.form["channel_id"]
    channel_name = request.form["channel_name"]
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


    channel_name = request.form["channel_name"]

    # Save stats
    with shelve.open('stats', writeback=True) as db:
        victim_name = victim['username']
        kicker_name = request.form['user_name']
        db['randomkick'].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "channel_name": channel_name,
            "kicker": kicker_name,
            "victim": victim_name
        })

    # Kick them
    mm.remove_user_from_channel(channel, victim["id"])
    return f"You just killed @{victim['username']}, do you feel happy now?"

@app.route("/russianroulette", methods=["POST"])
def russianroulette():
    # Make sure the bot is in the channel
    channel = request.form["channel_id"]
    channel_name = request.form["channel_name"]

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

    # Save stats
    with shelve.open('stats', writeback=True) as db:
        player_name = request.form['user_name']
        db['randomkick'].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "channel_name": channel_name,
            "player": player_name,
            "died": message == "_click_"
        })

    return jsonify({
            "response_type": "in_channel", 
            "text": message
    })

@app.route("/duel", methods=["POST"])
def duel():

    # Get the channel, the user and the victim
    channel = request.form['channel_id']
    channel_name = request.form["channel_name"]
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

    # Make sure the victim is in the channel
    channel_members = set([x["user_id"] for x in mm.get_channel_members(channel)])
    if victim['id'] not in channel_members:
        return f"@{victim['username']} is not in this channel"

    with GAME_MUTEX:
        mm.create_post(channel, f"@{caller_name} challenges @{victim['username']} for a game of russian roulette")

        # If it ducks like a quack
        players = [{"username": caller_name, "id": caller}, victim]
        game_tick = 0
        time.sleep(3)
        someone_died = False

        while(not someone_died and game_tick < max_game_ticks):

            player = players[game_tick % 2]

            # 1/6 chance...
            if random.randint(0,5) == 0 or game_tick == 1:
                mm.create_post(channel, f"@{player['username']} takes the gun... **BANG**!")
                someone_died = True
            else:
                mm.create_post(channel, f"@{player['username']} takes the gun... _click_")
                game_tick -= 1
                time.sleep(3)
                               
        mm.remove_user_from_channel(channel, player["id"])

    # Save stats
    with shelve.open('stats', writeback=True) as db:
        db['randomkick'].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "channel_name": channel_name,
            "starter": caller_name,
            "victim": victim_name,
            "gameTick": game_tick
        })

    return "https://www.youtube.com/watch?v=h1PfrmCGFnk"   

@app.route("/insult", methods=["POST"])
def insult():
    # Verify that there is an argument
    if request.form['text'] == '':
        return "Use /insult (name) to insult another user"

    insult = random.choice(list_of_insults)
    
    # Save stats
    with shelve.open('stats', writeback=True) as db:
        channel_name = request.form['channel_name']
        insulter = request.form['user_name']
        db['randomkick'].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "channel_name": channel_name,
            "insulter": insulter,
            "insultee": insultee,
            "insult": insult
        })

    return jsonify({
            "response_type": "in_channel", 
            "text": f"{request.form['text']}, {insult}"
    })

@app.route("/stats", methods=["GET"])
def stats():
    ret = {}
    with shelve.open("stats") as db:
        ret = dict(db)
    return jsonify(ret)

# Based on the mattermost library, but that has no "since" argument
def get_posts_for_channel(channel_id, since):
    data_page = mm._get("/v4/channels/"+channel_id+"/posts", params={"since":str(since)})

    for order in data_page["order"]:
        yield data_page["posts"][order]
