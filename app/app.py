from flask import Flask, jsonify, request
from os import path
import subprocess
import json
import os

app = Flask(__name__)

# Reading directory path from config.json file
with open('config.json') as json_data_file:
    config = json.load(json_data_file)
    WORKSPACE_DIR = config["path1"]

# Route for creating workspaces
@app.route('/workspace/create', methods=['POST'])
def linchpin_init():
    data = request.json     # Get request body
    name = data["name"]
    cmd = "linchpin init" + " " + name
    os.chdir(WORKSPACE_DIR)  # Change directory to the one set in config.json
    if path.isdir(name):
        return jsonify(status="Workspace already exists")   # Checking if workspace already exists

    else:
        subprocess.run(cmd, shell=True)  # run the command linchpin init on command line
        return jsonify(name=data["name"], status="Workspace created successfully")


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
