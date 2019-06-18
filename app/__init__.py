from flask import Flask, jsonify, request, Response
import subprocess
import os
import yaml

import shutil
import json
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

# Reading directory path from config.json file

with open('config.yml', 'r') as f:
    doc = yaml.load(f)

WORKING_DIR = doc['working_path']
LOGGER_FILE = doc['logger_file_name']

# Route for creating workspaces
@app.route('/workspace/create', methods=['POST'])
def linchpin_init():
    try:
        data = request.json     # Get request body
        name = data["name"]
        if os.path.exists(WORKING_DIR + "/" + name):
            return jsonify(status="Workspace already exists")   # Checking if workspace already exists
        else:
            output = subprocess.Popen(["linchpin", "-w " + WORKING_DIR + name + "/",  "init"], stdout=subprocess.PIPE)
            return jsonify(name=data["name"], status="Workspace created successfully", Code=output.returncode)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=409, code=output.returncode)

# Route for listing all workspaces
@app.route('/workspace/list', methods=['GET'])
def linchpin_list_workspace():
    try:
        workspace_array = []
        # path specifying location of working directory inside server
        for x in os.listdir(os.path.join(app.root_path + WORKING_DIR)):
            if os.path.isdir(x):
                workspace_dict = {'name ': x}
                workspace_array.append(workspace_dict)
        return Response(json.dumps(workspace_array), status=200, mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=409, message=str(e))


@app.route('/workspace/delete', methods=['POST'])
def linchpin_delete_workspace():
    try:
        data = request.json  # Get request body
        name = data["name"]
        # path specifying location of working directory inside server
        for x in os.listdir(os.path.join(app.root_path + WORKING_DIR)):
            if x == name:
                shutil.rmtree(name)
                return jsonify(name=name, status="Workspace deleted successfully")
        return jsonify(status="Workspace " + name + " not found")
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=409, message=str(e))


@app.route('/workspace/fetch', methods=['POST'])
def linchpin_fetch_workspace():
    try:
        data = request.json  # Get request body
        name = data['name']
        url = data['url']
        repo = None
        # initial list
        cmd = ["linchpin", "-w " + WORKING_DIR + name + "/", "fetch"]

        # Check for repoType field in request,
        # Only true if it is set to web
        if 'repoType' in data:
            if data['repoType'] == 'web':
                repo = 'web'
                cmd.append("--web")

        if 'rootfolder' in data:
            cmd.extend(("--root", data['rootfolder']))

        if repo is None and 'branch' in data:
            cmd.extend(("--branch", data['branch']))

        # last item to be added in the array
        if 'url' in data:
            cmd.append(str(url))
        # Checking if workspace already exists
        if os.path.exists(os.path.join(app.root_path, WORKING_DIR + "/" + name)):
            return jsonify(status="workspace with the same name found try again by renaming")
        else:
            output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            if check_workspace_empty(name):
                return jsonify(message="Only public repositories can be used as fetch URl's")
            return jsonify(name=data["name"], status="Workspace created successfully", code=output.returncode)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=409, message=str(e))


def check_workspace_empty(name):
    return os.listdir(app.root_path + WORKING_DIR + name) == []


if __name__ == "__main__":
    handler = RotatingFileHandler(LOGGER_FILE, maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.run(host='0.0.0.0', debug=True)





