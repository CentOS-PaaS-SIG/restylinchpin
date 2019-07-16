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
from flask import Flask, jsonify, request, Response
from flask_swagger_ui import get_swaggerui_blueprint
from utils import get_connection, create_fetch_cmd, create_cmd_workspace,\
    create_cmd_up_pinfile, check_workspace_empty


app = Flask(__name__)

APP_DIR = os.path.dirname(os.path.realpath(__file__))
# Reading directory path from config.yml file
with open(APP_DIR + '/config.yml', 'r') as f:
    config = yaml.load(f)

WORKSPACE_DIR = config.get('workspace_path', '/tmp/')
LOGGER_FILE = config.get('logger_file_name', 'restylinchpin.log')
DB_PATH = config.get('db_path', 'db.json')
INVENTORY_PATH = config.get('inventory_path', '/dummy/inventories/*')
LATEST_PATH = config.get('linchpin_latest_file_path',
                         '/dummy/resources/linchpin.latest')
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
        'app_name': "restylinchpin"
    }
)

# path navigating to current workspace directory
WORKSPACE_PATH = os.path.normpath(app.root_path + WORKSPACE_DIR + r' ')


# Route for creating workspaces
@app.route('/workspace/create', methods=['POST'])
def linchpin_init() -> Response:
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
                             response.WORKSPACE_REQUESTED)
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
@app.route('/workspace/list', methods=['GET'])
def linchpin_list_workspace() -> Response:
    """
        GET request route for listing workspaces.
        :return : response with a list of workspaces
        from the destination set in config.py
    """
    db_con = get_connection(DB_PATH)
    try:
        workspace_array = db_con.db_list_all()
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
    db_con = get_connection(DB_PATH)
    try:
        workspace = db_con.db_search(name)
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
    db_con = get_connection(DB_PATH)
    try:
        # path specifying location of working directory inside server
        for x in os.listdir(WORKSPACE_PATH):
            if x == identity:
                shutil.rmtree(WORKSPACE_PATH + "/" + x)
                db_con.db_remove(identity)
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


@app.route('/workspace/fetch', methods=['POST'])
def linchpin_fetch_workspace() -> Response:
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
                             response.WORKSPACE_REQUESTED)
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
    db_con = get_connection(DB_PATH)

    try:
        data = request.json  # Get request body
        provision_type = data['provision_type']
        if provision_type == "workspace":
            identity = data['id']
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
                                     response.WORKSPACE_REQUESTED)
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


@app.route('/workspace/destroy', methods=['POST'])
def linchpin_destroy() -> Response:
    """
        POST request route for destroying workspaces/resources already created
        or provisioned
        RequestBody: {"id": "workspace_id"}
        :return : response with destroyed workspace id and status
    """
    identity = None
    db_con = get_connection(DB_PATH)
    try:
        data = request.json  # Get request body
        identity = data['id']
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
    handler = RotatingFileHandler(LOGGER_FILE,
                                  maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.run(host='0.0.0.0', debug=True)
