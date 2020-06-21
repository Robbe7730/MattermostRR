#!/usr/bin/env python

import mattermost
import mattermost.ws

from flask import request
from flask import Flask
app = Flask(__name__)

import configparser
import sys

# Read in the config
config = configparser.ConfigParser()
config.read('config.ini')

# Setup Mattermost connection
mm = mattermost.MMApi(config["mattermost"]["url"])
mm.login(bearer=config["mattermost"]["token"])
user = mm.get_user()

def eprint(msg):
    print(msg, file=sys.stderr)

@app.route("/russianroulette", methods=["POST"])
def russian_roulette():
    # Make sure the bot is in the channel
    channel = request.form["channel_id"]
    mm.add_user_to_channel(channel, user["id"])
    return "PANG"
