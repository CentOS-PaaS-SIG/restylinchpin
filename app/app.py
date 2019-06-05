from flask import Flask, jsonify, request
from os import path
import subprocess
import json
import os

app = Flask(__name__)

with open('config.json') as json_data_file:
    config = json.load(json_data_file)
    workspace_dir = config["path1"]


@app.route('/workspace/create', methods=['POST'])
def linchpin_init():
    data = request.json
    name = data["name"]
    cmd = "linchpin init" + " " + name
    os.chdir(workspace_dir)
    if path.isdir(name):
        return jsonify(status="Workspace already exists")
    else:
        subprocess.run(cmd, shell=True)
        return jsonify(name=data["name"], status="Workspace created successfully")


if __name__ == "__main__":
    app.run()
