from typing import List, Any, Union

from flask import Flask, jsonify, request, Response
import subprocess
import os
import yaml
from flask_swagger_ui import get_swaggerui_blueprint
import shutil
import json
import logging
from logging.handlers import RotatingFileHandler
from dal import dbConn
from config import errors, response

app = Flask(__name__)

# Reading directory path from config.yml file

with open('config.yml', 'r') as f:
    doc = yaml.load(f)

with open('swagger.json', 'r') as f:
    jsonData = json.load(f)

WORKING_DIR = doc['working_path']
LOGGER_FILE = doc['logger_file_name']

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

# Route for creating workspaces
@app.route('/workspace/create', methods=['POST'])
def linchpin_init() -> Response:
    """
        POST request route for creating workspaces.
        RequestBody: {"name": "workspacename"}
        :return : response with created workspace name,
                  status and code
    """
    try:
        data = request.json     # Get request body
        name = data["name"]
        # Checking if workspace already exists
        if os.path.exists(WORKING_PATH + "/" + name):
            return jsonify(status=response.DUPLICATE_WORKSPACE)
        else:
            output = subprocess.Popen(["linchpin", "-w " +
                                       WORKING_DIR + name +
                                       "/", "init"], stdout=subprocess.PIPE)
            dbConn.db_insert(name)
            return jsonify(name=data["name"],
                           status=response.CREATE_SUCCESS,
                           Code=output.returncode, mimetype='application/json')
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_NAME)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e),
                       code=output.returncode)


# Route for listing all workspaces
@app.route('/workspace/list', methods=['GET'])
def linchpin_list_workspace() -> Response:
    """
        GET request route for listing workspaces.
        :return : response with a list of workspaces
        from the destination set in config.py
    """
    try:
        workspace_array = []
        # path specifying location of working directory inside server
        for x in os.listdir(WORKING_PATH):
            if os.path.isdir(WORKING_PATH + "/" + x):
                workspace_dict = {'name ': x}
                workspace_array.append(workspace_dict)
        return Response(json.dumps(workspace_array), status=200,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/workspace/delete', methods=['POST'])
def linchpin_delete_workspace() -> Response:
    """
        POST request route for deleting workspaces.
        RequestBody: {"name": "workspacename"}
        :return : response with deleted workspace name and status
    """
    try:
        data = request.json  # Get request body
        name = data["name"]
        # path specifying location of working directory inside server
        for x in os.listdir(WORKING_PATH):
            if x == name:
                shutil.rmtree(WORKING_PATH + "/" + name)
                dbConn.db_remove(name)
                return jsonify(name=name,
                               status=response.DELETE_SUCCESS,
                               mimetype='application/json')
        return jsonify(status=response.NOT_FOUND)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_NAME)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


def create_fetch_cmd(data) -> List[str]:
    """
        Creates a list to feed the subprocess in fetch API
        :param data: JSON data from POST requestBody
        :return a list for the subprocess to run
    """
    name = data['name']
    url = data['url']
    repo = None
    # initial list
    cmd = ["linchpin", "-w " + WORKING_DIR + name, "fetch"]

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
        RequestBody: {"name": "workspacename", "url": "www.github.com/someurl",
        "rootfolder":"/path/to/folder"}
        :return : response with fetched workspace name,status and code
    """
    try:
        data = request.json  # Get request body
        name = data['name']
        cmd = create_fetch_cmd(data)
        # Checking if workspace already exists
        if os.path.exists(WORKING_PATH + "/" + name):
            return jsonify(status=response.DUPLICATE_WORKSPACE)
        else:
            output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            output.communicate()
            if check_workspace_empty(name):
                return jsonify(status=response.EMPTY_WORKSPACE)
            dbConn.db_insert(name)
            return jsonify(name=data["name"], status=response.CREATE_SUCCESS,
                           code=output.returncode, mimetype='application/json')
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_PARAMS)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


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
