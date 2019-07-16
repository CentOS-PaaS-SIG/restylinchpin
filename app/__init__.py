import os
import re
import glob
import yaml
import json
import uuid
import shutil
import logging
import subprocess
from typing import List
import data_access_layer.RestDB
from response_messages import errors, response
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request, Response
from flask_swagger_ui import get_swaggerui_blueprint

app = Flask(__name__)

# Reading directory path from config.yml file
with open('config.yml', 'r') as f:
    config = yaml.load(f)

WORKING_DIR = config.get('working_path', '/tmp/')

LOGGER_FILE = config.get('logger_file_name', 'restylinchpin.log')
DB_PATH = config.get('db_path', 'db.json')
INVENTORY_PATH = config.get('inventory_path','/dummy/inventories/*')
LATEST_PATH = config.get('linchpin_latest_file_path', '/dummy/resources/linchpin.latest')
PINFILE_JSON_PATH = config.get('pinfile_json_path', '/dummy/PinFile.json')

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
    return data_access_layer.RestDB.RestDB(DB_PATH)

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
                       message=errors.KEY_ERROR_PARAMS_FETCH)


def create_cmd_workspace(data, identity, action) -> List[str]:
    """
        Creates a list to feed the subprocess for provisioning/
        destroying existing workspaces
        :param data: JSON data from POST requestBody
        :param identity: unique uuid_name assigned to the workspace
        :param action: up or destroy action
        :return a list for the subprocess to run
    """
    if 'pinfile_path' in data:
        pinfile_path = data['pinfile_path']
        check_path = identity + pinfile_path
    else:
        check_path = identity
    cmd = ["linchpin", "-w " + WORKING_DIR + check_path]
    if 'pinfileName' in data:
        cmd.extend(("-p", data['pinfileName']))
        pinfile_name = data['pinfileName']
    else:
        pinfile_name = "PinFile"
    if not check_workspace_has_pinfile(check_path, pinfile_name):
        return jsonify(status=response.PINFILE_NOT_FOUND)
    cmd.append(action)
    if 'tx_id' in data:
        cmd.extend(("-t", data['tx_id']))
    elif 'run_id' and 'target' in data:
        cmd.extend(("-r", data['run_id'], data['target']))
    if 'inventory_format' in data:
        cmd.extend(("--if", data['inventory_format']))
    return cmd


def create_cmd_up_pinfile(data, identity) -> List[str]:
    """
        Creates a list to feed the subprocess for provisioning
        new workspaces instantiated using a pinfile
        :param data: JSON data from POST requestBody
        :param identity: unique uuid_name assigned to the workspace
        :return a list for the subprocess to run
    """
    pinfile_content = data['pinfile_content']
    json_pinfile_path = WORKING_PATH + "/" + identity + PINFILE_JSON_PATH
    with open(json_pinfile_path, 'w') as json_data:
        json.dump(pinfile_content, json_data)
    cmd = ["linchpin", "-w " + WORKING_DIR + identity + "/dummy", "-p" +
           "PinFile.json", "up"]
    if 'inventory_format' in data:
        cmd.extend(("--if", data['inventory_format']))
    return cmd


@app.route('/workspace/up', methods=['POST'])
def linchpin_up() -> Response:
    """
        POST request route for provisioning workspaces/pinFile already created
        RequestBody: {"id": "workspace_id",
                    provision_type: "workspace",
                    --> value can be either pinfile or workspace
                    }
        :return : response with provisioned workspace id, status,
                  contents_of_latest_inventory_generated_in_inventoryfolder,
                  contents_of_linchpin.latest_file_in_resource_folder
    """
    identity = None
    try:
        data = request.json  # Get request body
        provision_type = data['provision_type']
        if provision_type == "workspace":
            identity = data['id']
            if not os.path.exists(WORKING_PATH + "/" + identity):
                return jsonify(status=response.NOT_FOUND)
            cmd = create_cmd_workspace(data, identity, "up")
        elif provision_type == "pinfile":
            if 'name' in data:
                identity = str(uuid.uuid4()) + "_" + data['name']
            else:
                identity = str(uuid.uuid4())
            precmd = ["linchpin", "-w " + WORKING_DIR + identity +
                      "/", "init"]
            output = subprocess.Popen(precmd, stdout=subprocess.PIPE)
            output.communicate()
            get_connection().db_insert_no_name(identity,
                                               response.WORKSPACE_REQUESTED)
            cmd = create_cmd_up_pinfile(data, identity)
        else:
            raise ValueError
        output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        output.communicate()
        linchpin_latest_path = WORKING_PATH + "/" + identity + LATEST_PATH
        with open(linchpin_latest_path, 'r') as file:
            linchpin_latest = json.load(file)
        directory_path = glob.glob(WORKING_PATH + "/" + identity +
                                   INVENTORY_PATH)
        latest_file = max(directory_path, key=os.path.getctime)
        with open(latest_file, 'r') as data:
            inventory = data.read().replace('\n', ' ')
        get_connection().db_update(identity, response.PROVISION_STATUS_SUCCESS)
        return jsonify(id=identity,
                       status=response.PROVISION_SUCCESS,
                       inventory=inventory,
                       latest=linchpin_latest,
                       code=output.returncode,
                       mimetype='application/json')
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_UP)
    except Exception as e:
        get_connection().db_update(identity, response.PROVISION_FAILED)
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/workspace/destroy', methods=['POST'])
def linchpin_destroy() -> Response:
    """
        POST request route for destroying workspaces/resources already created
        or provisioned
        RequestBody: {"id": "workspace_id"}
        :return : response with destroyed workspace id and status
    """
    identity = None
    try:
        data = request.json  # Get request body
        identity = data['id']
        cmd = create_cmd_workspace(data, identity, "destroy")
        output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        output.communicate()
        get_connection().db_update(identity, response.DESTROY_STATUS_SUCCESS)
        return jsonify(id=identity,
                       status=response.DESTROY_SUCCESS,
                       code=output.returncode,
                       mimetype='application/json')
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_DESTROY)
    except Exception as e:
        get_connection().db_update(identity, response.DESTROY_FAILED)
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


def check_workspace_has_pinfile(name, pinfile_name) -> bool:
    """
        Verifies if a workspace to be provisioned contains a PinFile.json
        :param name: name of the workspace to be verified
        :param pinfile_name: name of pinfile in directory
        :return a boolean value True or False
    """
    return os.listdir(WORKING_PATH + "/" + name).__contains__(pinfile_name)


def check_workspace_empty(name) -> bool:
    """
        Verifies if a workspace fetched/created is empty
        :param name: name of the workspace to be verified
        :return a boolean value True or False
    """
    return os.listdir(WORKING_PATH + "/" + name) == []


if __name__ == "__main__":
    handler = RotatingFileHandler(LOGGER_FILE,
                                  maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.run(host='0.0.0.0', debug=True)
