#!/usr/bin/env python

import mattermost
import mattermost.ws

from flask import Flask
app = Flask(__name__)

import configparser
import sys

def eprint(msg):
    print(msg, file=sys.stderr)

mm = None
user = None

def main():
    # Read in the config
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    # Setup Mattermost connection
    mm = mattermost.MMApi(config["mattermost"]["url"])
    mm.login(bearer=config["mattermost"]["token"])
    user = mm.get_user()

    # Check for team id
    if "team_id" not in config["mattermost"]:
        available_teams = mm.get_teams()
        eprint("No team_id set in config.ini, please select one:")
        for team in available_teams:
            eprint(f" - {team['display_name']}: {team['id']}")
        return

@app.route("/russianroulette")
def russian_roulette():
    data = request.get_json()
    channel = data["channel_id"]
    mm.add_user_to_channel(user["id"], channel)
    return "PANG"

if __name__ == "__main__":
    main()
