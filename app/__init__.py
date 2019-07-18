import os
import re
import glob
import yaml
import json
import uuid
import shutil
import logging
import subprocess
from response_messages import errors, response
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request, Response, abort, make_response
import data_access_layer.UserRestDB
import data_access_layer.RestDB
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_swagger_ui import get_swaggerui_blueprint
from utils import get_connection, create_fetch_cmd, create_cmd_workspace,\
    create_cmd_up_pinfile, check_workspace_empty, get_connection_users

app = Flask(__name__)

APP_DIR = os.path.dirname(os.path.realpath(__file__))

try:
    with open(APP_DIR + '/config.yml', 'r') as f:
        config = yaml.load(f)
except Exception as e:
    config = {}
    app.logger.error(e)


# loads defaults when config.yml does not exists or has been removed
WORKSPACE_DIR = config.get('workspace_path', '/tmp/')
LOGGER_FILE = config.get('logger_file_name', 'restylinchpin.log')
USERS_DB_PATH = config.get('users_db_path', 'users.json')
DB_PATH = config.get('db_path', 'db.json')
INVENTORY_PATH = config.get('inventory_path', '/dummy/inventories/*')
LATEST_PATH = config.get('linchpin_latest_file_path',
                         '/dummy/resources/linchpin.latest')
PINFILE_JSON_PATH = config.get('pinfile_json_path', '/dummy/PinFile.json')
ADMIN_USERNAME = config.get('admin_username', 'admin')
ADMIN_PASSWORD = config.get('admin_password', 'password')

# URL for exposing Swagger UI (without trailing '/')
SWAGGER_URL = '/api/docs'
# Our API url (can of course be a local resource)
API_URL = 'https://api.myjson.com/bins/m95ah'

# Call factory function to create our blueprint
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={  # Swagger UI config overrides
        'app_name': "restylinchpin"
    }
)

# path navigating to current workspace directory
WORKSPACE_PATH = os.path.normpath(app.root_path + WORKSPACE_DIR + r' ')


def token_required(function):
    @wraps(function)
    def decorated(*args, **kwargs):
        db_con = get_connection(DB_PATH)
        token = None
        if 'Token' in request.headers:
            token = request.headers['Token']
        if not token:
            return jsonify(response.TOKEN_MISSING)
        try:
            current_user = db_con.db_get_api_key(token)
            if current_user is None:
                return jsonify(response.TOKEN_INVALID)
        except Exception as e:
            return jsonify(message=response.TOKEN_INVALID, statu=e)
        return function(current_user, *args, **kwargs)
    return decorated


def create_admin_user():
    db_con = get_connection(DB_PATH)
    username = ADMIN_USERNAME
    password = ADMIN_PASSWORD
    if db_con.db_get_username(username):
        return
    hashed_password = generate_password_hash(password, method='sha256')
    hashed_api_key = generate_password_hash(str(uuid.uuid4()), method='sha256')
    admin = True
    db_con.db_insert(username, hashed_password, hashed_api_key, admin)


@app.route('/api/v1.0/users', methods=['POST'])
@token_required
def new_user(current_user):
    db_con = get_connection(DB_PATH)
    if not current_user['admin']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    username = request.json.get('username')
    password = request.json.get('password')
    email = request.json.get('email')
    api_key = str(uuid.uuid4())
    if username is None or password is None:
        abort(errors.ERROR_STATUS)    # missing arguments
    if db_con.db_get_username(username):
        return jsonify(message=response.USER_ALREADY_EXISTS)
    hashed_password = generate_password_hash(password, method='sha256')
    hashed_api_key = generate_password_hash(api_key, method='sha256')
    admin = False
    db_con.db_insert(username, hashed_password, hashed_api_key, email, admin)
    return jsonify(username=username, email=email,
                   admin=admin, status=response.STATUS_OK)


@app.route('/api/v1.0/login')
def login():
    db_con = get_connection(DB_PATH)
    authorize = request.authorization
    if not authorize or not authorize.username or not authorize.password:
        return make_response(response.AUTH_FAILED)

    user = db_con.db_get_username(authorize.username)

    if not user:
        return make_response(response.AUTH_FAILED)

    if check_password_hash(user['password'], authorize.password):
        token = user['api_key']
        return jsonify(token=token)

    return make_response(response.AUTH_FAILED)


@app.route('/api/v1.0/users/<username>')
@token_required
def get_user(current_user, username):
    db_con = get_connection(DB_PATH)
    if not current_user['admin'] and not current_user['username'] == username:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = db_con.db_search_name(username)
    if not user:
        abort(errors.ERROR_STATUS)
    return jsonify(username=username,
                   api_key=current_user['api_key'],
                   admin=current_user['admin'])


@app.route('/api/v1.0/users')
@token_required
def get_users(current_user):
    db_con = get_connection(DB_PATH)
    if not current_user['admin']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    users = db_con.db_list_all()
    return Response(json.dumps(users), status=response.STATUS_OK,
                    mimetype='application/json')


@app.route('/api/v1.0/users', methods=['PUT'])
@token_required
def promote_user(current_user, username):
    db_con = get_connection(DB_PATH)
    if not current_user['admin']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = db_con.db_get_username(username)
    if not user:
        return jsonify(response.USER_NOT_FOUND)
    db_con.db_update_admin(username, True)
    return jsonify(message=response.USER_PROMOTED)


@app.route('/api/v1.0/users/<user_name>', methods=['PUT'])
@token_required
def update_user(current_user, user_name):
    db_con = get_connection(DB_PATH)
    if not current_user['admin'] and not current_user['username'] == user_name:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = db_con.db_get_username(user_name)
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
    db_con.db_update(user_name, username, hashed_password, email)
    return jsonify(username=username, email=email, password=hashed_password,
                   status=response.STATUS_OK)


@app.route('/api/v1.0/users/<username>', methods=['DELETE'])
@token_required
def delete_user(current_user, username):
    db_con = get_connection(DB_PATH)
    if not current_user['admin'] and not current_user['username'] == username:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    user = db_con.db_search_name(username)
    if not user:
        abort(errors.ERROR_STATUS)
    db_con.db_remove(username)
    return jsonify(message=response.USER_DELETED)


@app.route('/api/v1.0/users', methods=['DELETE'])
@token_required
def delete_api_key(current_user):
    db_con = get_connection(DB_PATH)
    api_key = request.args.get('api_key', None)
    user = db_con.db_get_api_key(api_key)
    if not current_user['admin'] and not current_user['username'] == user['username']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    db_con.db_remove_api_key(api_key)
    return jsonify(message=response.API_KEY_DELETED)


@app.route('/api/v1.0/users', methods=['PUT'])
@token_required
def reset_api_key(current_user):
    db_con = get_connection(DB_PATH)
    username = request.args.get('username', None)
    user = db_con.db_get_username(username)
    if not current_user['admin'] and not current_user['password'] == user['password']:
        return jsonify(message=errors.UNAUTHORIZED_REQUEST)
    hashed_new_api_key = generate_password_hash(str(uuid.uuid4()), method='sha256')
    db_con.db_reset_api_key(username, hashed_new_api_key)
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
    db_con = get_connection(DB_PATH)
    try:
        data = request.json  # Get request body
        name = data["name"]
        identity = str(uuid.uuid4()) + "_" + name
        try:
            db_con.db_insert(identity, name,
                                       response.WORKSPACE_REQUESTED, current_user['username'])

            if not re.match("^[a-zA-Z0-9]*$", name):
                db_con.db_update(identity, response.WORKSPACE_FAILED)
                return jsonify(status=errors.ERROR_STATUS,
                               message=errors.INVALID_NAME)
            else:
                # Checking if workspace name contains any special characters
                output = subprocess.Popen(["linchpin", "-w " +
                                          WORKSPACE_DIR + identity +
                                          "/", "init"], stdout=subprocess.PIPE)
                db_con.db_update(identity, response.WORKSPACE_SUCCESS)
                return jsonify(name=data["name"], id=identity,
                               status=response.CREATE_SUCCESS,
                               Code=output.returncode,
                               mimetype='application/json')
        except Exception as e:
            db_con.db_update(identity, response.WORKSPACE_FAILED)
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
    db_con = get_connection(DB_PATH)
    try:
        admin = False
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        workspace_array = db_con.db_list_all(current_user['username'], admin)
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
    db_con = get_connection(DB_PATH)
    try:
        admin = False
        workspace_owner_user = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace_owner_user:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        workspace = db_con.db_search(name, admin, current_user['username'])
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
    db_con = get_connection(DB_PATH)
    try:
        # path specifying location of working directory inside server
        admin = False
        workspace_owner_user = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace_owner_user:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        else:
            workspace = db_con.db_search_identity(identity)
            if not db_con.db_search(workspace['name'], admin, current_user['username']):
                return jsonify(response.NOT_FOUND)
        for x in os.listdir(WORKSPACE_PATH):
            if x == identity:
                shutil.rmtree(WORKSPACE_PATH + "/" + x)
                db_con.db_remove(identity, admin, current_user['username'])
                return jsonify(id=identity,
                               status=response.DELETE_SUCCESS,
                               mimetype='application/json')
        return jsonify(status=response.NOT_FOUND)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))



@app.route('/api/v1.0/workspaces/fetch', methods=['POST'])
@token_required
def linchpin_fetch_workspace(current_user) -> Response:
    """
        POST request route for fetching workspaces from a remote URL
        RequestBody: {"name": "workspacename","url": "www.github.com/someurl",
        "rootfolder":"/path/to/folder"}
        :return : response with fetched workspace name,id, status and code
    """
    db_con = get_connection(DB_PATH)
    try:
        data = request.json  # Get request body
        name = data['name']
        identity = str(uuid.uuid4()) + "_" + name
        try:
            db_con.db_insert(identity, name,
                                       response.WORKSPACE_REQUESTED, current_user['username'])
            cmd = create_fetch_cmd(data, identity, WORKSPACE_DIR)
            # Checking if workspace name contains special characters
            if not re.match("^[a-zA-Z0-9]*$", name):
                db_con.db_update(identity, response.WORKSPACE_FAILED)
                return jsonify(status=errors.ERROR_STATUS,
                               message=errors.INVALID_NAME)
            else:
                output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                output.communicate()
                if check_workspace_empty(identity, WORKSPACE_PATH):
                    db_con.db_update(identity,
                                     response.WORKSPACE_FAILED)
                    return jsonify(status=response.EMPTY_WORKSPACE)
                db_con.db_update(identity,
                                 response.WORKSPACE_SUCCESS)
                return jsonify(name=data["name"], id=identity,
                               status=response.CREATE_SUCCESS,
                               code=output.returncode,
                               mimetype='application/json')
        except Exception as e:
            db_con.db_update(identity, response.WORKSPACE_FAILED)
            app.logger.error(e)
            return jsonify(status=errors.ERROR_STATUS, message=str(e))
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_PARAMS_FETCH)


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
    db_con = get_connection(DB_PATH)
    try:
        admin = False
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        data = request.json  # Get request body
        provision_type = data['provision_type']
        if provision_type == "workspace":
            identity = data['id']
            if not admin:
                workspace = db_con.db_search_identity(identity)
                if not db_con.db_search(workspace['name'], admin, current_user['username']):
                    return jsonify(message=response.NOT_FOUND)
            if not os.path.exists(WORKSPACE_PATH + "/" + identity):
                return jsonify(status=response.NOT_FOUND)
            cmd = create_cmd_workspace(data, identity, "up",
                                       WORKSPACE_PATH, WORKSPACE_DIR)
        elif provision_type == "pinfile":
            if 'name' in data:
                identity = str(uuid.uuid4()) + "_" + data['name']
            else:
                identity = str(uuid.uuid4())
            precmd = ["linchpin", "-w " + WORKSPACE_DIR + identity +
                      "/", "init"]
            output = subprocess.Popen(precmd, stdout=subprocess.PIPE)
            output.communicate()
            db_con.db_insert_no_name(identity,
                                               response.WORKSPACE_REQUESTED, current_user['username'])
            cmd = create_cmd_up_pinfile(data, identity, WORKSPACE_PATH,
                                        WORKSPACE_DIR, PINFILE_JSON_PATH)
        else:
            raise ValueError
        output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        output.communicate()
        linchpin_latest_path = WORKSPACE_PATH + "/" + identity + LATEST_PATH
        with open(linchpin_latest_path, 'r') as file:
            linchpin_latest = json.load(file)
        directory_path = glob.glob(WORKSPACE_PATH + "/" + identity +
                                   INVENTORY_PATH)
        latest_file = max(directory_path, key=os.path.getctime)
        with open(latest_file, 'r') as data:
            inventory = data.read().replace('\n', ' ')
        db_con.db_update(identity, response.PROVISION_STATUS_SUCCESS)
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
        db_con.db_update(identity, response.PROVISION_FAILED)
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
    db_con = get_connection(DB_PATH)
    try:
        admin = False
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if current_user['admin']:
            admin = True
        data = request.json  # Get request body
        identity = data['id']
        if not admin:
            workspace = db_con.db_search_identity(identity)
            if not db_con.db_search(workspace['name'], admin, current_user['username']):
                return jsonify(message=response.NOT_FOUND)
        cmd = create_cmd_workspace(data, identity, "destroy", WORKSPACE_DIR)
        output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        output.communicate()
        db_con.db_update(identity, response.DESTROY_STATUS_SUCCESS)
        return jsonify(id=identity,
                       status=response.DESTROY_SUCCESS,
                       code=output.returncode,
                       mimetype='application/json')
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR_DESTROY)
    except Exception as e:
        db_con.db_update(identity, response.DESTROY_FAILED)
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


if __name__ == "__main__":
    create_admin_user()
    handler = RotatingFileHandler(LOGGER_FILE,
                                  maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.run(host='0.0.0.0', debug=True)
