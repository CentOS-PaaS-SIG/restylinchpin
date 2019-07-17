from typing import List
from flask import Flask, jsonify, request, Response, abort, make_response
import subprocess
import glob
import os
import yaml
from flask_swagger_ui import get_swaggerui_blueprint
import shutil
import json
import logging
import re
import uuid
from logging.handlers import RotatingFileHandler
import data_access_layer.UserRestDB
import data_access_layer.RestDB
from config import errors, response
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)

# Reading directory path from config.yml file

with open('config.yml', 'r') as f:
    doc = yaml.load(f)

with open('swagger.json', 'r') as f:
    jsonData = json.load(f)

WORKING_DIR = doc['working_path']
LOGGER_FILE = doc['logger_file_name']
WORKSPACE_DB_PATH = doc['workspace_db_path']
USERS_DB_PATH = doc['users_db_path']
INVENTORY_PATH = doc['inventory_path']
LATEST_PATH = doc['linchpin_latest_file_path']
PINFILE_JSON_PATH = doc['pinfile_json_path']
ADMIN_USERNAME = doc['admin_username']
ADMIN_PASSWORD = doc['admin_password']

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
    return data_access_layer.RestDB.RestDB(WORKSPACE_DB_PATH)


def get_connection_users():
    """
        Method to create an object of subclass and create a connection
        :return : an instantiated object for class UserRestDB
    """
    return data_access_layer.UserRestDB.UserRestDB(USERS_DB_PATH)


def token_required(function):
    @wraps(function)
    def decorated(*args, **kwargs):
        token = None
        if 'Token' in request.headers:
            token = request.headers['Token']
        if not token:
            return jsonify(response.TOKEN_MISSING)
        try:
            current_user = get_connection_users().db_get_api_key(token)
            if current_user is None:
                return jsonify(response.TOKEN_INVALID)
        except Exception as e:
            return jsonify(message=response.TOKEN_INVALID, statu=e)
        return function(current_user, *args, **kwargs)
    return decorated


def create_admin_user():
    username = ADMIN_USERNAME
    password = ADMIN_PASSWORD
    if get_connection_users().db_get_username(username):
        return
    hashed_password = generate_password_hash(password, method='sha256')
    hashed_api_key = generate_password_hash(str(uuid.uuid4()), method='sha256')
    admin = True
    get_connection_users().db_insert(username, hashed_password, hashed_api_key, admin)


@app.route('/api/v1.0/users', methods=['POST'])
@token_required
def new_user(current_user):
    if not current_user['admin']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    username = request.json.get('username')
    password = request.json.get('password')
    email = request.json.get('email')
    api_key = str(uuid.uuid4())
    if username is None or password is None:
        abort(errors.ERROR_STATUS)    # missing arguments
    if get_connection_users().db_get_username(username):
        return jsonify(message=response.USER_ALREADY_EXISTS)
    hashed_password = generate_password_hash(password, method='sha256')
    hashed_api_key = generate_password_hash(api_key, method='sha256')
    admin = False
    get_connection_users().db_insert(username, hashed_password, hashed_api_key, email, admin)
    return jsonify(username=username, email=email,
                   admin=admin, status=response.STATUS_OK)


@app.route('/api/v1.0/login')
def login():
    authorize = request.authorization
    if not authorize or not authorize.username or not authorize.password:
        return make_response(response.AUTH_FAILED)

    user = get_connection_users().db_get_username(authorize.username)

    if not user:
        return make_response(response.AUTH_FAILED)

    if check_password_hash(user['password'], authorize.password):
        token = user['api_key']
        return jsonify(token=token)

    return make_response(response.AUTH_FAILED)


@app.route('/api/v1.0/users/<username>')
@token_required
def get_user(current_user, username):
    if not current_user['admin'] and not current_user['username'] == username:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = get_connection_users().db_search_name(username)
    if not user:
        abort(errors.ERROR_STATUS)
    return jsonify(username=username,
                   api_key=current_user['api_key'],
                   admin=current_user['admin'])


@app.route('/api/v1.0/users')
@token_required
def get_users(current_user):
    if not current_user['admin']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    users = get_connection_users().db_list_all()
    return Response(json.dumps(users), status=response.STATUS_OK,
                    mimetype='application/json')


@app.route('/api/v1.0/users', methods=['PUT'])
@token_required
def promote_user(current_user, username):
    if not current_user['admin']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = get_connection_users().db_get_username(username)
    if not user:
        return jsonify(response.USER_NOT_FOUND)
    get_connection_users().db_update_admin(username, True)
    return jsonify(message=response.USER_PROMOTED)


@app.route('/api/v1.0/users/<user_name>', methods=['PUT'])
@token_required
def update_user(current_user, user_name):
    if not current_user['admin'] and not current_user['username'] == user_name:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = get_connection_users().db_get_username(user_name)
    if not user:
        return jsonify(response.USER_NOT_FOUND)
    hashed_password = user['password']
    email = user['email']
    data = request.json
    if 'username' in data:
        username = request.json.get('username')
    else:
        username = user_name
    if 'password' in data:
        password = request.json.get('password')
        hashed_password = generate_password_hash(password, method='sha256')
    if 'email' in data:
        email = request.json.get('email')
    get_connection_users().db_update(user_name, username, hashed_password, email)
    return jsonify(username=username, email=email, password=hashed_password,
                   status=response.STATUS_OK)


@app.route('/api/v1.0/users/<username>', methods=['DELETE'])
@token_required
def delete_user(current_user, username):
    if not current_user['admin'] and not current_user['username'] == username:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = get_connection_users().db_search_name(username)
    if not user:
        abort(errors.ERROR_STATUS)
    get_connection_users().db_remove(username)
    return jsonify(message=response.USER_DELETED)


@app.route('/api/v1.0/users', methods=['DELETE'])
@token_required
def delete_api_key(current_user):
    api_key = request.args.get('api_key', None)
    user = get_connection_users().db_get_api_key(api_key)
    if not current_user['admin'] and not current_user['username'] == user['username']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    get_connection_users().db_remove_api_key(api_key)
    return jsonify(message=response.API_KEY_DELETED)


@app.route('/api/v1.0/users', methods=['PUT'])
@token_required
def reset_api_key(current_user):
    username = request.args.get('username', None)
    user = get_connection_users().db_get_username(username)
    if not current_user['admin'] and not current_user['password'] == user['password']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    hashed_new_api_key = generate_password_hash(str(uuid.uuid4()), method='sha256')
    get_connection_users().db_reset_api_key(username, hashed_new_api_key)
    return jsonify(message=response.API_KEY_RESET)

# Route for creating workspaces
@app.route('/api/v1.0/workspaces', methods=['POST'])
@token_required
def linchpin_init(current_user) -> Response:
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
                                       response.WORKSPACE_REQUESTED, current_user['username'])
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
@app.route('/api/v1.0/workspaces', methods=['GET'])
@token_required
def linchpin_list_workspace(current_user) -> Response:
    """
        GET request route for listing workspaces.
        :return : response with a list of workspaces
        from the destination set in config.py
    """
    try:
        admin = False
        workspace = get_connection().db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        workspace_array = get_connection().db_list_all(current_user['username'], admin)
        # path specifying location of working directory inside server
        return Response(json.dumps(workspace_array), status=response.STATUS_OK,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))

# Route for listing workspaces filtered by name
@app.route('/api/v1.0/workspaces/<name>', methods=['GET'])
@token_required
def linchpin_list_workspace_by_name(current_user, name) -> Response:
    """
        GET request route for listing workspaces by name
        :return : response with a list of workspaces filtered by name
    """
    try:
        admin = False
        workspace_owner_user = get_connection().db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace_owner_user:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        workspace = get_connection().db_search(name, admin, current_user['username'])
        # path specifying location of working directory inside server
        return Response(json.dumps(workspace), status=response.STATUS_OK,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))

# Route for deleting workspaces by Id
@app.route('/api/v1.0/workspaces/<identity>', methods=['DELETE'])
@token_required
def linchpin_delete_workspace(current_user, identity) -> Response:
    """
        DELETE request route for deleting workspaces.
        :param : unique uuid_name assigned to the workspace
        :return : response with deleted workspace id and status
    """
    try:
        # path specifying location of working directory inside server
        admin = False
        workspace_owner_user = get_connection().db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace_owner_user:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        else:
            workspace = get_connection().db_search_identity(identity)
            if not get_connection().db_search(workspace['name'], admin, current_user['username']):
                return jsonify(response.NOT_FOUND)
        for x in os.listdir(WORKING_PATH):
            if x == identity:
                shutil.rmtree(WORKING_PATH + "/" + x)
                get_connection().db_remove(identity, admin, current_user['username'])
                return jsonify(id=identity,
                               status=response.DELETE_SUCCESS,
                               mimetype='application/json')
        return jsonify(status=response.NOT_FOUND)
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


@app.route('/api/v1.0/workspaces/fetch', methods=['POST'])
@token_required
def linchpin_fetch_workspace(current_user) -> Response:
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
                                       response.WORKSPACE_REQUESTED, current_user['username'])
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


@app.route('/api/v1.0/workspaces/up', methods=['POST'])
@token_required
def linchpin_up(current_user) -> Response:
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
        admin = False
        workspace = get_connection().db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        data = request.json  # Get request body
        provision_type = data['provision_type']
        if provision_type == "workspace":
            identity = data['id']
            if not admin:
                workspace = get_connection().db_search_identity(identity)
                if not get_connection().db_search(workspace['name'], admin, current_user['username']):
                    return jsonify(message=response.NOT_FOUND)
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
                                               response.WORKSPACE_REQUESTED, current_user['username'])
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


@app.route('/api/v1.0/workspaces/destroy', methods=['POST'])
@token_required
def linchpin_destroy(current_user) -> Response:
    """
        POST request route for destroying workspaces/resources already created
        or provisioned
        RequestBody: {"id": "workspace_id"}
        :return : response with destroyed workspace id and status
    """
    identity = None
    try:
        admin = False
        workspace = get_connection().db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        data = request.json  # Get request body
        identity = data['id']
        if not admin:
            workspace = get_connection().db_search_identity(identity)
            if not get_connection().db_search(workspace['name'], admin, current_user['username']):
                return jsonify(message=response.NOT_FOUND)
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
    create_admin_user()
    handler = RotatingFileHandler(LOGGER_FILE,
                                  maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.run(host='0.0.0.0', debug=True)
