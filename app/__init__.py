import os
import re
import glob
import yaml
import json
import uuid
import shutil
import logging
import subprocess
from ansible_vault import Vault
from app.response_messages import response, errors
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request, Response, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_swagger_ui import get_swaggerui_blueprint
from functools import wraps
from app.utils import get_connection, create_fetch_cmd, create_cmd_workspace,\
    create_cmd_up_pinfile, check_workspace_empty, get_connection_users, \
    create_admin_user, check_workspace_has_pinfile

app = Flask(__name__)

APP_DIR = os.path.dirname(os.path.realpath(__file__))

try:
    with open(APP_DIR + '/config.yml', 'r') as f:
        config = yaml.load(f)
except Exception as x:
    config = {}
    app.logger.error(x)


# loads defaults when config.yml does not exists or has been removed
WORKSPACE_DIR = config.get('workspace_path', '/')
LOGGER_FILE = config.get('logger_file_name', 'restylinchpin.log')
DB_PATH = config.get('db_path', 'db.json')
INVENTORY_PATH = config.get('inventory_path', '/dummy/inventories/*')
LATEST_PATH = config.get('linchpin_latest_file_path',
                         '/dummy/resources/linchpin.latest')
PINFILE_JSON_PATH = config.get('pinfile_json_path', '/dummy/PinFile.json')
LINCHPIN_LATEST_NAME = config.get('linchpin_latest_name', 'linchpin.latest')
ADMIN_USERNAME = config.get('admin_username', 'admin')
ADMIN_PASSWORD = config.get('admin_password', 'password')
ADMIN_EMAIL = config.get('admin_email', 'email')
CREDS_PATH = config.get('creds_path', '/')

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


def auth_required(function):
    @wraps(function)
    def decorated(*args, **kwargs):
        """
            Method to verify api_key before making each request
            :return : returns successful route if success else
                        api-key invalid message
        """
        db_con = get_connection_users(DB_PATH)
        api_key = None
        if 'api_key' in request.headers:
            api_key = request.headers['api_key']
        if not api_key:
            return jsonify(response.API_KEY_MISSING)
        try:
            current_user = db_con.db_get_api_key(api_key)
            if current_user is None:
                return jsonify(response.API_KEY_INVALID)
        except Exception as e:
            return jsonify(message=response.API_KEY_INVALID, status=e)
        return function(current_user, *args, **kwargs)
    return decorated


@app.route('/api/v1.0/users', methods=['POST'])
@auth_required
def new_user(current_user):
    """
        POST request route for creating users.
        :return : response with created username,
                    email, admin status.
    """
    db_con = get_connection_users(DB_PATH)
    try:
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
        db_con.db_insert(username, hashed_password,
                         hashed_api_key, email, admin)
        return jsonify(username=username, email=email,
                       admin=admin, status=response.STATUS_OK)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/login')
def login():
    """
        GET request route for user login
        :return : response with API KEY to be used for making request
    """
    db_con = get_connection_users(DB_PATH)
    try:
        authorize = request.authorization
        if not authorize or not authorize.username \
                or not authorize.password:
            return make_response(response.AUTH_FAILED)
        user = db_con.db_get_username(authorize.username)
        if not user:
            return make_response(response.AUTH_FAILED)
        if check_password_hash(user['password'], authorize.password):
            api_key = user['api_key']
            return jsonify(api_key=api_key)
        return make_response(response.AUTH_FAILED)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/users/<username>')
@auth_required
def get_user(current_user, username):
    """
        GET request route for retrieving user details
        :return : response with user's username, api_key,
                    email, admin status.
    """
    db_con = get_connection_users(DB_PATH)
    try:
        if not current_user['admin'] and \
                not current_user['username'] == username:
            return jsonify(message=errors.UNAUTHORIZED_REQUEST)
        user = db_con.db_search_name(username)
        if not user:
            abort(errors.ERROR_STATUS)
        return jsonify(username=username,
                       api_key=current_user['api_key'],
                       email=current_user['email'],
                       admin=current_user['admin'])
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/users')
@auth_required
def get_users(current_user):
    """
        GET request route for retrieving all users
        :return : response with list of all users
                  present in db.
    """
    db_con = get_connection_users(DB_PATH)
    try:
        if not current_user['admin']:
            return jsonify(message=errors.UNAUTHORIZED_REQUEST)
        users = db_con.db_list_all()
        return Response(json.dumps(users), status=response.STATUS_OK,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/users', methods=['DELETE'])
@auth_required
def delete_api_key(current_user):
    """
        DELETE request route for deleting a user's API key
        Request args are accepted as /api/v1.0/users?api_key=value
        :return : response with success message
    """
    db_con = get_connection_users(DB_PATH)
    try:
        api_key = request.args.get('api_key')
        user = db_con.db_get_api_key(api_key)
        if not user:
            return jsonify(message=response.MISSING_API_KEY)
        if not current_user['admin'] and not \
                current_user['username'] == user['username']:
            return jsonify(message=errors.UNAUTHORIZED_REQUEST)
        db_con.db_remove_api_key(api_key)
        return jsonify(message=response.API_KEY_DELETED)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/users/<username>/reset', methods=['POST'])
def reset_api_key(username):
    """
         POST request route for resetting/adding a user's API key
         Request args are accepted as /api/v1.0/users?username=value
         Authentication is done using basic auth username, password
         :return : response with success message and new api_key value
    """
    db_con = get_connection_users(DB_PATH)
    try:
        authorize = request.authorization
        user = db_con.db_get_username(username)
        if not user:
            return jsonify(message=response.MISSING_USERNAME)
        if not authorize or not authorize.username == user['username'] or \
                not authorize.password == user['password'] and \
                not authorize.username == ADMIN_USERNAME \
                or not authorize.password == ADMIN_PASSWORD:
            return jsonify(message=errors.UNAUTHORIZED_REQUEST)
        hashed_new_api_key = \
            generate_password_hash(str(uuid.uuid4()), method='sha256')
        db_con.db_reset_api_key(username, hashed_new_api_key)
        return jsonify(message=response.API_KEY_RESET,
                       api_key=hashed_new_api_key)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/users/<username>/promote', methods=['PUT'])
@auth_required
def promote_user(current_user, username):
    """
        PUT request route for promoting a user to admin status
        :return : response with success message.
    """
    db_con = get_connection_users(DB_PATH)
    try:
        if not current_user['admin']:
            return jsonify(message=errors.UNAUTHORIZED_REQUEST)
        user = db_con.db_get_username(username)
        if not user:
            return jsonify(response.USER_NOT_FOUND)
        db_con.db_update_admin(username, True)
        return jsonify(message=response.USER_PROMOTED)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/users/<user_name>', methods=['PUT'])
@auth_required
def update_user(current_user, user_name):
    """
        PUT request route for updating a user's details
        :return : response with a list of fields updated
                  for user.
    """
    db_con = get_connection_users(DB_PATH)
    try:
        if not current_user['admin'] and \
                not current_user['username'] == user_name:
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
            hashed_password = generate_password_hash(password,
                                                     method='sha256')
        if 'email' in data:
            email = request.json.get('email')
        db_con.db_update(user_name, username, hashed_password, email)
        return jsonify(username=username, email=email,
                       password=hashed_password,
                       status=response.STATUS_OK)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/users/<username>', methods=['DELETE'])
@auth_required
def delete_user(current_user, username):
    """
        DELETE request route for deleting a user with given username
        :return : response with success message
    """
    db_con = get_connection_users(DB_PATH)
    try:
        if not current_user['admin'] and \
                not current_user['username'] == username:
            return jsonify(message=errors.UNAUTHORIZED_REQUEST)
        user = db_con.db_search_name(username)
        if not user:
            abort(errors.ERROR_STATUS)
        db_con.db_remove(username)
        return jsonify(message=response.USER_DELETED)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


# Route for creating workspaces
@app.route('/api/v1.0/workspaces', methods=['POST'])
@auth_required
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
                             response.WORKSPACE_REQUESTED,
                             current_user['username'])

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
@auth_required
def linchpin_list_workspace(current_user) -> Response:
    """
        GET request route for listing workspaces.
        :return : response with a list of workspaces
        from the destination set in config.py
    """
    db_con = get_connection(DB_PATH)
    try:
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        workspace_array = db_con.db_list_all(current_user['username'],
                                             current_user['admin'])
        # path specifying location of working directory inside server
        return Response(json.dumps(workspace_array), status=response.STATUS_OK,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


# Route for listing workspaces filtered by name
@app.route('/api/v1.0/workspaces/<name>', methods=['GET'])
@auth_required
def linchpin_list_workspace_by_name(current_user, name) -> Response:
    """
        GET request route for listing workspaces by name
        :return : response with a list of workspaces filtered by name
    """
    db_con = get_connection(DB_PATH)
    try:
        workspace_owner_user = \
            db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace_owner_user:
            return jsonify(message=response.NOT_FOUND)
        workspace = db_con.db_search(name, current_user['admin'],
                                     current_user['username'])
        # path specifying location of working directory inside server
        return Response(json.dumps(workspace), status=response.STATUS_OK,
                        mimetype='application/json')
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


# Route for deleting workspaces by Id
@app.route('/api/v1.0/workspaces/<identity>', methods=['DELETE'])
@auth_required
def linchpin_delete_workspace(current_user, identity) -> Response:
    """
        DELETE request route for deleting workspaces.
        :param : unique uuid_name assigned to the workspace
        :return : response with deleted workspace id and status
    """
    db_con = get_connection(DB_PATH)
    try:
        # path specifying location of working directory inside server
        workspace_owner_user =\
            db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace_owner_user:
            return jsonify(message=response.NOT_FOUND)
        if not current_user['admin']:
            workspace = db_con.db_search_identity(identity)
            if not db_con.db_search(workspace['name'], current_user['admin'],
                                    current_user['username']):
                return jsonify(response.NOT_FOUND)
        for w in os.listdir(WORKSPACE_PATH):
            if w == identity:
                shutil.rmtree(WORKSPACE_PATH + "/" + w)
                db_con.db_remove(identity, current_user['admin'],
                                 current_user['username'])
                return jsonify(id=identity,
                               status=response.DELETE_SUCCESS,
                               mimetype='application/json')
        return jsonify(status=response.NOT_FOUND)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/workspaces/fetch', methods=['POST'])
@auth_required
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
                             response.WORKSPACE_REQUESTED,
                             current_user['username'])
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
@auth_required
def linchpin_up(current_user) -> Response:
    """
        POST request route for provisioning workspaces/pinFile already
        created
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
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        data = request.json  # Get request body
        provision_type = data['provision_type']
        if provision_type == "workspace":
            identity = data['id']
            if not current_user['admin']:
                workspace = db_con.db_search_identity(identity)
                if not db_con.db_search(workspace['name'],
                                        current_user['admin'],
                                        current_user['username']):
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
                                     response.WORKSPACE_REQUESTED,
                                     current_user['username'])
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
                       message=errors.KEY_ERROR)
    except Exception as e:
        db_con.db_update(identity, response.PROVISION_FAILED)
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/workspaces/destroy', methods=['POST'])
@auth_required
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
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        data = request.json  # Get request body
        identity = data['id']
        if not current_user['admin']:
            workspace = db_con.db_search_identity(identity)
            if not db_con.db_search(workspace['name'], current_user['admin'],
                                    current_user['username']):
                return jsonify(message=response.NOT_FOUND)
        cmd = create_cmd_workspace(data, identity, "destroy", WORKSPACE_PATH,
                                   WORKSPACE_DIR)
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


@app.route('/api/v1.0/workspaces/<identity>', methods=['PUT'])
@auth_required
def linchpin_update_pinfile(current_user, identity) -> Response:
    """
        PUT request route for updating a pinfile's contents
        RequestBody: { pinfile_content:{json file contents},
                       pinfile_name:name,
                       pinfile_path:path_to_pinfile }
       return : response with successful pinfile updation status
    """
    db_con = get_connection(DB_PATH)
    try:
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if not current_user['admin']:
            workspace = db_con.db_search_identity(identity)
            if not db_con.db_search(workspace['name'], current_user['admin'],
                                    current_user['username']):
                return jsonify(message=response.NOT_FOUND)
        data = request.json
        pinfile_content = data['pinfile_content']
        if 'pinfile_path' in data:
            pinfile_path = data['pinfile_path']
            check_path = identity + pinfile_path
        else:
            check_path = identity
        if 'pinfile_name' in data:
            pinfile_name = data['pinfile_name']
        else:
            pinfile_name = "PinFile.json"
        json_pinfile_path = WORKSPACE_PATH + "/" + check_path + pinfile_name
        if not check_workspace_has_pinfile(check_path, pinfile_name,
                                           WORKSPACE_PATH):
            return jsonify(status=response.PINFILE_NOT_FOUND)
        with open(json_pinfile_path, 'w') as json_data:
            json.dump(pinfile_content, json_data)
        return jsonify(message=response.PINFILE_UPDATED)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/workspaces/<identity>/linchpin_latest', methods=['POST'])
@auth_required
def get_linchpin_latest(current_user, identity) -> Response:
    """
        POST request route for getting linchpin.latest file from user's
        provisioned workspace
        RequestBody: { linchpin_latest_path:path_to_linchpin.latest }
        return : response with workspace id and linchpin.latest file contents
    """
    db_con = get_connection(DB_PATH)
    try:
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if not current_user['admin']:
            workspace = db_con.db_search_identity(identity)
            if not db_con.db_search(workspace['name'], current_user['admin'],
                                    current_user['username']):
                return jsonify(message=response.NOT_FOUND)
        data = request.json
        if 'linchpin_latest_path' in data:
            linchpin_latest_path = data['linchpin_latest_path']
            check_path = linchpin_latest_path
        else:
            check_path = "/"
        linchpin_latest_directory = WORKSPACE_PATH + "/" + identity + check_path
        if not os.listdir(linchpin_latest_directory).\
                __contains__(LINCHPIN_LATEST_NAME):
            return jsonify(message=response.LINCHPIN_LATEST_NOT_FOUND)
        linchpin_latest_path = linchpin_latest_directory + LINCHPIN_LATEST_NAME
        with open(linchpin_latest_path, 'r') as file:
            linchpin_latest = json.load(file)
        return jsonify(id=identity,
                       latest=linchpin_latest)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/workspaces/<identity>/inventory', methods=['POST'])
@auth_required
def get_linchpin_inventory(current_user, identity) -> Response:
    """
        POST request route for getting contents of all inventory files from
        user's provisioned workspace
        RequestBody: { linchpin_inventory_path:path_to_inventories_folder }
        return : response with workspace id and all inventory files contents
    """
    db_con = get_connection(DB_PATH)
    try:
        workspace = db_con.db_search_username(current_user['username'])
        if not current_user['admin'] and not workspace:
            return jsonify(message=response.NOT_FOUND)
        if not current_user['admin']:
            workspace = db_con.db_search_identity(identity)
            if not db_con.db_search(workspace['name'], current_user['admin'],
                                    current_user['username']):
                return jsonify(message=response.NOT_FOUND)
        data = request.json
        inventory_list = []
        if 'linchpin_inventory_path' in data:
            linchpin_inventory_path = data['linchpin_inventory_path']
            check_path = linchpin_inventory_path + "*"
        else:
            check_path = "/*"
        directory_path = glob.glob(WORKSPACE_PATH + "/" + identity +
                                   check_path)
        for i in range(0, len(directory_path), 1):
            with open(directory_path[i], 'r') as data:
                inventory = data.read().replace('\n', ' ')
            inventory_list.append(inventory)
        return jsonify(id=identity,
                       inventory=inventory_list)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/credentials', methods=['POST'])
@auth_required
def upload_credentials(current_user) -> Response:
    db_con = get_connection_users(DB_PATH)
    try:
        user = db_con.db_search_name(current_user['username'])
        if not user:
            return jsonify(message=response.USER_NOT_FOUND)
        file_name = request.form['file_name']
        encrypted = request.form['encrypted']
        if request.form["creds_folder_name"]:
            creds_folder = request.form["creds_folder_name"]
        else:
            if current_user['creds_folder'] is None:
                creds_folder = current_user['username'] + "_" + str(uuid.uuid4())
                db_con.db_update_creds_folder(current_user['username'],
                                              creds_folder)
                os.makedirs(WORKSPACE_PATH + CREDS_PATH + creds_folder)
            else:
                creds_folder = current_user['creds_folder']
        if request.files:
            file = request.files["file"]
            file_read = file.read()
        else:
            file_read = request.form["file"]
        if encrypted.lower() in ("true", "t"):
            if request.files:
                with open(WORKSPACE_PATH + CREDS_PATH + creds_folder + "/" + file_name + ".yml", 'wb') as yaml_file:
                    yaml_file.write(file_read)
            else:
                with open(WORKSPACE_PATH + CREDS_PATH + creds_folder + "/" + file_name + ".yml", 'w') as yaml_file:
                    yaml_file.write(file_read)
        else:
            vault_pass = request.form['vault_pass']
            vault = Vault(vault_pass)
            vault.dump(file_read, open(WORKSPACE_PATH + CREDS_PATH + creds_folder + "/" + file_name + ".yml", 'wb'))
        return jsonify(message=response.CREDENTIALS_UPLOADED)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/credentials/<file_name>', methods=['GET'])
@auth_required
def get_credentials(current_user, file_name) -> Response:
    db_con = get_connection_users(DB_PATH)
    try:
        user = db_con.db_search_name(current_user['username'])
        if not user:
            return jsonify(message=response.USER_NOT_FOUND)
        if not os.listdir(WORKSPACE_PATH + CREDS_PATH + current_user['creds_folder']). \
                __contains__(file_name):
            return jsonify(message=response.CREDENTIALS_FILE_NOT_FOUND)
        with open(WORKSPACE_PATH + CREDS_PATH + current_user['creds_folder'] +
                  "/" + file_name, 'r') as data:
            credentials = data.read().replace('\n', ' ')
        return jsonify(credentials=credentials)
    except (KeyError, ValueError, TypeError):
        return jsonify(status=errors.ERROR_STATUS,
                       message=errors.KEY_ERROR)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/credentials/<file_name>', methods=['PUT'])
@auth_required
def update_credentials(current_user, file_name) -> Response:
    db_con = get_connection_users(DB_PATH)
    try:
        user = db_con.db_search_name(current_user['username'])
        if not user:
            return jsonify(message=response.USER_NOT_FOUND)
        if 'creds_folder_name' not in request.form:
            creds_folder = current_user['creds_folder']
        else:
            creds_folder = request.form['creds_folder_name']
        if not os.listdir(WORKSPACE_PATH + CREDS_PATH + creds_folder). \
                __contains__(file_name):
            return jsonify(message=response.CREDENTIALS_FILE_NOT_FOUND)
        if request.files:
            file = request.files["file"]
            file_read = file.read()
        else:
            file_read = request.form["file"]
        encrypted = request.form['encrypted']
        if encrypted.lower() in ("true", "t"):
            if request.files:
                with open(WORKSPACE_PATH + CREDS_PATH + creds_folder + "/" + file_name, 'wb') as yaml_file:
                    yaml_file.write(file_read)
            else:
                with open(WORKSPACE_PATH + CREDS_PATH + creds_folder + "/" + file_name, 'w') as yaml_file:
                    yaml_file.write(file_read)
        else:
            vault_pass = request.form['vault_pass']
            vault = Vault(vault_pass)
            vault.dump(file_read, open(WORKSPACE_PATH + CREDS_PATH + creds_folder + "/" + file_name, 'wb'))
        return jsonify(message=response.CREDENTIALS_UPDATED)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


@app.route('/api/v1.0/credentials/<file_name>', methods=['DELETE'])
@auth_required
def delete_credentials(current_user, file_name) -> Response:
    db_con = get_connection_users(DB_PATH)
    try:
        user = db_con.db_search_name(current_user['username'])
        if not user:
            return jsonify(message=response.USER_NOT_FOUND)
        if 'creds_folder_name' not in request.form:
            creds_folder = current_user['creds_folder']
        else:
            creds_folder = request.form['creds_folder_name']
        for w in os.listdir(WORKSPACE_PATH + CREDS_PATH + creds_folder):
            print(w)
            if w == file_name:
                print("here")
                os.remove(WORKSPACE_PATH + CREDS_PATH + creds_folder + "/" + w)
                print("deleted")
                return jsonify(status=response.CREDENTIALS_DELETED,
                               mimetype='application/json')
        return jsonify(status=response.CREDENTIALS_FILE_NOT_FOUND)
    except Exception as e:
        app.logger.error(e)
        return jsonify(status=errors.ERROR_STATUS, message=str(e))


if __name__ == "__main__":
    create_admin_user(DB_PATH, ADMIN_USERNAME,
                      ADMIN_PASSWORD, ADMIN_EMAIL)
    handler = RotatingFileHandler(LOGGER_FILE,
                                  maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.run(host='0.0.0.0', debug=True)
