from typing import List
from flask import Flask, jsonify, request, Response
import subprocess
import os
import yaml
from flask_swagger_ui import get_swaggerui_blueprint
import shutil
import json
import logging
import re
import uuid
from logging.handlers import RotatingFileHandler
import dal.RestDB
from config import errors, response

app = Flask(__name__)

# Reading directory path from config.yml file

with open('config.yml', 'r') as f:
    doc = yaml.load(f)

with open('swagger.json', 'r') as f:
    jsonData = json.load(f)

WORKING_DIR = doc['working_path']
LOGGER_FILE = doc['logger_file_name']
DB_PATH = doc['db_path']

# URL for exposing Swagger UI (without trailing '/')
SWAGGER_URL = '/api/docs'
# Our API url (can of course be a local resource)
API_URL = 'https://api.myjson.com/bins/m95ah'

# Call factory function to create our blueprint
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={  # Swagger UI config overrides
        'app_name': "Test application"
    }
)

# path navigating to current workspace directory
WORKING_PATH = os.path.normpath(app.root_path + WORKING_DIR + r' ')


def get_connection():
    """
        Method to create an object of subclass and create a connection
        :return : an instantiated object for class RestDB
    """
    return dal.RestDB.RestDB(DB_PATH)

# Route for creating workspaces
@app.route('/workspace/create', methods=['POST'])
def linchpin_init() -> Response:
    """
        POST request route for creating workspaces.
        RequestBody: {"name": "workspacename"}
        :return : response with created workspace name,
                  id, status and code
    """
    try:
        data = request.json  # Get request body
        name = data["name"]
        identity = str(uuid.uuid4()) + "_" + name
        try:
            get_connection().db_insert(identity, name,
                                       response.WORKSPACE_REQUESTED)
            if not re.match("^[a-zA-Z0-9]*$", name):
                get_connection().db_update(identity, response.WORKSPACE_FAILED)
                return jsonify(status=errors.ERROR_STATUS,
                               message=errors.INVALID_NAME)
            else:
                # Checking if workspace name contains any special characters
                output = subprocess.Popen(["linchpin", "-w " +
                                          WORKING_DIR + identity +
                                          "/", "init"], stdout=subprocess.PIPE)
                get_connection().db_update(identity, response.WORKSPACE_SUCCESS)
                return jsonify(name=data["name"], id=identity,
                               status=response.CREATE_SUCCESS,
                               Code=output.returncode,
                               mimetype='application/json')
        except Exception as e:
            get_connection().db_update(identity, response.WORKSPACE_FAILED)
            app.logger.error(e)
            return jsonify(status=errors.ERROR_STATUS, message=str(e))
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_NAME)


# Route for listing all workspaces
@app.route('/workspace/list', methods=['GET'])
def linchpin_list_workspace() -> Response:
    """
        GET request route for listing workspaces.
        :return : response with a list of workspaces
        from the destination set in config.py
    """
    try:
        workspace_array = get_connection().db_list_all()
        # path specifying location of working directory inside server
        return Response(json.dumps(workspace_array), status=200,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))

# Route for listing workspaces filtered by name
@app.route('/workspace/list/<name>', methods=['GET'])
def linchpin_list_workspace_by_name(name) -> Response:
    """
        GET request route for listing workspaces by name
        :return : response with a list of workspaces filtered by name
    """
    try:
        workspace = get_connection().db_search(name)
        # path specifying location of working directory inside server
        return Response(json.dumps(workspace), status=200,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))

# Route for deleting workspaces by Id
@app.route('/workspace/delete/<identity>', methods=['DELETE'])
def linchpin_delete_workspace(identity) -> Response:
    """
        DELETE request route for deleting workspaces.
        :param : unique uuid_name assigned to the workspace
        :return : response with deleted workspace id and status
    """
    try:
        # path specifying location of working directory inside server
        for x in os.listdir(WORKING_PATH):
            if x == identity:
                shutil.rmtree(WORKING_PATH + "/" + x)
                get_connection().db_remove(identity)
                return jsonify(id=identity,
                               status=response.DELETE_SUCCESS,
                               mimetype='application/json')
        return jsonify(status=response.NOT_FOUND)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_NAME)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


def create_fetch_cmd(data, identity) -> List[str]:
    """
        Creates a list to feed the subprocess in fetch API
        :param data: JSON data from POST requestBody
        :param identity: unique uuid_name assigned to the workspace
        :return a list for the subprocess to run
    """
    url = data['url']
    repo = None
    # initial list
    cmd = ["linchpin", "-w " + WORKING_DIR + identity, "fetch"]

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
    return cmd


@app.route('/workspace/fetch', methods=['POST'])
def linchpin_fetch_workspace() -> Response:
    """
        POST request route for fetching workspaces from a remote URL
        RequestBody: {"name": "workspacename","url": "www.github.com/someurl",
        "rootfolder":"/path/to/folder"}
        :return : response with fetched workspace name,id, status and code
    """
    try:
        data = request.json  # Get request body
        name = data['name']
        identity = str(uuid.uuid4()) + "_" + name
        try:
            get_connection().db_insert(identity, name,
                                       response.WORKSPACE_REQUESTED)
            cmd = create_fetch_cmd(data, identity)
            # Checking if workspace name contains special characters
            if not re.match("^[a-zA-Z0-9]*$", name):
                get_connection().db_update(identity, response.WORKSPACE_FAILED)
                return jsonify(status=errors.ERROR_STATUS,
                               message=errors.INVALID_NAME)
            else:
                output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                output.communicate()
                if check_workspace_empty(identity):
                    get_connection().db_update(identity,
                                               response.WORKSPACE_FAILED)
                    return jsonify(status=response.EMPTY_WORKSPACE)
                get_connection().db_update(identity,
                                           response.WORKSPACE_SUCCESS)
                return jsonify(name=data["name"], id=identity,
                               status=response.CREATE_SUCCESS,
                               code=output.returncode,
                               mimetype='application/json')
        except Exception as e:
            get_connection().db_update(identity, response.WORKSPACE_FAILED)
            app.logger.error(e)
            return jsonify(status=errors.ERROR_STATUS, message=str(e))
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_PARAMS)


def check_workspace_empty(name) -> bool:
    """
        Verifies if a workspace fetched/created is empty
        :param name: name of the workspace to be verified
        :return a boolean value True or False
    """
    return os.listdir(WORKING_PATH + "/" + name) == []


if __name__ == "__main__":
    handler = RotatingFileHandler(LOGGER_FILE, maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.run(host='0.0.0.0', debug=True)
