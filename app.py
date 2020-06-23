#!/usr/bin/env python

import mattermost

from flask import request
from flask import Flask, jsonify
app = Flask(__name__)

import configparser
import sys
import time
import random
import shelve

# Read in the config
config = configparser.ConfigParser()
config.read('config.ini')

# Setup Mattermost connection
mm = mattermost.MMApi(config["mattermost"]["url"])
mm.login(bearer=config["mattermost"]["token"])
user = mm.get_user()

# Setup russian roulette config
active_users_since = int(config["russianroulette"]["active_users_since_minutes"])

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
    mm.create_post(channel, f"Goodbye @{victim['username']}")

    # Save stats
    with shelve.open('randomkick') as db:
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
    with shelve.open('russianroulette') as db:
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

# Based on the mattermost library, but that has no "since" argument
def get_posts_for_channel(channel_id, since):
    data_page = mm._get("/v4/channels/"+channel_id+"/posts", params={"since":str(since)})

    for order in data_page["order"]:
        yield data_page["posts"][order]
