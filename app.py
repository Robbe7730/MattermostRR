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

# Setup shelve storage
with shelve.open('russianroulette') as db:
    if 'channels' not in db:
        db['channels'] = {}
    if 'totals' not in db:
        db['totals'] = {}
    if 'deaths' not in db:
        db['deaths'] = {}
with shelve.open('randomkick') as db:
    if 'channels' not in db:
        db['channels'] = {}
    if 'victims' not in db:
        db['victims'] = {}
    if 'kickers' not in db:
        db['kickers'] = {}
with shelve.open('duel') as db:
    if 'channels' not in db:
        db['channels'] = {}
    if 'victims' not in db:
        db['victims'] = {}
    if 'starters' not in db:
        db['starters'] = {}
    if 'losers' not in db:
        db['losers'] = {}

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
    with shelve.open('randomkick', writeback=True) as db:
        # Channel randomkick count
        if channel_name not in db["channels"]:
            db["channels"][channel_name] = 0
        db["channels"][channel_name] += 1

        # Victim randomkick count
        victim_name = victim['username']
        if victim_name not in db["victims"]:
            db["victims"][victim_name] = 0
        db["victims"][victim_name] += 1

        # Kicker randomkick count
        kicker_name = request.form['user_name']
        if kicker_name not in db["kickers"]:
            db["kickers"][kicker_name] = 0
        db["kickers"][kicker_name] += 1

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
    with shelve.open('russianroulette', writeback=True) as db:
        # Channel rr count
        if channel_name not in db["channels"]:
            db["channels"][channel_name] = 0
        db["channels"][channel_name] += 1

        # Victim total count
        victim_name = request.form['user_name']
        if victim_name not in db["totals"]:
            db["totals"][victim_name] = 0
        db["totals"][victim_name] += 1

        # Victim death count
        if message == "_click_":
            if victim_name not in db["deaths"]:
                db["deaths"][victim_name] = 0
            db["deaths"][victim_name] += 1


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

    # Save stats
    with shelve.open('duel', writeback=True) as db:
        # Channel duel count
        if channel_name not in db["channels"]:
            db["channels"][channel_name] = 0
        db["channels"][channel_name] += 1

        # Victim duel count
        victim_name = victim['username']
        if victim_name not in db["victims"]:
            db["victims"][victim_name] = 0
        db["victims"][victim_name] += 1

        # Starter duel count
        starter_name = request.form['user_name']
        if starter_name not in db["starters"]:
            db["starters"][starter_name] = 0
        db["starters"][starter_name] += 1

        # Loser duel count
        loser_name = player["username"]
        if loser_name not in db["losers"]:
            db["losers"][loser_name] = 0
        db["losers"][loser_name] += 1

    return "https://www.youtube.com/watch?v=h1PfrmCGFnk"   

@app.route("/stats", methods=["GET"])
def stats():
    ret = {}
    with shelve.open('russianroulette') as db:
        ret['rr'] = dict(db)
    with shelve.open('randomkick') as db:
        ret['randomkick'] = dict(db)
    with shelve.open('duel') as db:
        ret['duel'] = dict(db)
    return jsonify(ret)

@app.route("/insult", methods=["POST"])
def insult():
    # Verify that there is an argument
    if request.form['text'] == '':
        return "Use /insult (name) to insult another user"

    return jsonify({
            "response_type": "in_channel", 
            "text": f"@{request.form['text']}, {random.choice(list_of_insults)}"
    })


# Based on the mattermost library, but that has no "since" argument
def get_posts_for_channel(channel_id, since):
    data_page = mm._get("/v4/channels/"+channel_id+"/posts", params={"since":str(since)})

    for order in data_page["order"]:
        yield data_page["posts"][order]
