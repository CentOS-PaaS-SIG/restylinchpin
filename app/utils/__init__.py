import os
import json
import uuid
from app.data_access_layer import RestDB
from app.data_access_layer import UserRestDB
from app.response_messages import response
from flask import jsonify
from typing import List
from werkzeug.security import generate_password_hash


def get_connection(db_path):
    """
        Method to create an object of subclass and create a connection
        :return : an instantiated object for class RestDB
    """
    return RestDB.RestDB(db_path)


def get_connection_users(db_path):
    """
        Method to create an object of subclass and create a connection
        :return : an instantiated object for class UserRestDB
    """
    return UserRestDB.UserRestDB(db_path)


def create_admin_user(users_db_path, admin_username, admin_password,
                      admin_email):
    """
        Method to create an admin user by default when app runs
        :return : an admin user record in db
    """
    db_con = get_connection_users(users_db_path)
    if db_con.db_get_username(admin_username):
        return
    hashed_password = generate_password_hash(admin_password, method='sha256')
    hashed_api_key = generate_password_hash(str(uuid.uuid4()), method='sha256')
    admin = True
    db_con.db_insert(admin_username, hashed_password, hashed_api_key,
                     admin_email, admin)


def create_fetch_cmd(data, identity, workspace_dir) -> List[str]:
    """
        Creates a list to feed the subprocess in fetch API
        :param data: JSON data from POST requestBody
        :param workspace_dir: Path of current workspace
        :param identity: unique uuid_name assigned to the workspace
        :return a list for the subprocess to run
    """
    url = data['url']
    repo = None
    # initial list
    cmd = ["linchpin", "-w " + workspace_dir + identity, "fetch"]

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


def create_cmd_workspace(data, identity, action,
                         workspace_path, workspace_dir,
                         creds_folder_path) -> List[str]:
    """
        Creates a list to feed the subprocess for provisioning/
        destroying existing workspaces
        :param data: JSON data from POST requestBody
        :param identity: unique uuid_name assigned to the workspace
        :param action: up or destroy action
        :param creds_folder_path: path to the credentials folder
        :return a list for the subprocess to run
    """
    if 'pinfile_path' in data:
        pinfile_path = data['pinfile_path']
        check_path = identity + pinfile_path
    else:
        check_path = identity
    cmd = ["linchpin", "-w " + workspace_dir + check_path]
    if 'creds_path' in data:
        cmd.extend(("--creds-path", data['creds_path']))
    else:
        cmd.extend(("--creds-path", creds_folder_path))
    if 'pinfile_name' in data:
        cmd.extend(("-p", data['pinfile_name']))
        pinfile_name = data['pinfile_name']
    else:
        pinfile_name = "PinFile"
    if not check_workspace_has_pinfile(check_path, pinfile_name,
                                       workspace_path):
        return jsonify(status=response.PINFILE_NOT_FOUND)
    cmd.append(action)
    if 'tx_id' in data:
        cmd.extend(("-t", data['tx_id']))
    elif 'run_id' and 'target' in data:
        cmd.extend(("-r", data['run_id'], data['target']))
    if 'inventory_format' in data:
        cmd.extend(("--if", data['inventory_format']))
    return cmd


def create_cmd_up_pinfile(data,
                          identity,
                          workspace_path,
                          workspace_dir,
                          pinfile_json_path,
                          creds_folder_path) -> List[str]:
    """
        Creates a list to feed the subprocess for provisioning
        new workspaces instantiated using a pinfile
        :param data: JSON data from POST requestBody
        :param identity: unique uuid_name assigned to the workspace
        :param creds_folder_path: path to the credentials folder
        :return a list for the subprocess to run
    """
    pinfile_content = data['pinfile_content']
    json_pinfile_path = workspace_path + "/" + identity + pinfile_json_path
    with open(json_pinfile_path, 'w') as json_data:
        json.dump(pinfile_content, json_data)
    cmd = ["linchpin", "-w " + workspace_dir + identity + "/dummy", "-p" +
           "PinFile.json"]
    if 'creds_path' in data:
        cmd.extend(("--creds-path", data['creds_path']))
    else:
        cmd.extend(("--creds-path", creds_folder_path))
    cmd.append("up")
    if 'inventory_format' in data:
        cmd.extend(("--if", data['inventory_format']))
    return cmd


def check_workspace_has_pinfile(name, pinfile_name, workspace_path) -> bool:
    """
        Verifies if a workspace to be provisioned contains a PinFile.json
        :param name: name of the workspace to be verified
        :param pinfile_name: name of pinfile in directory
        :return a boolean value True or False
    """
    return os.listdir(workspace_path + "/" + name).__contains__(pinfile_name)


def check_workspace_empty(name, workspace_path) -> bool:
    """
        Verifies if a workspace fetched/created is empty
        :param name: name of the workspace to be verified
        :return a boolean value True or False
    """
    return os.listdir(workspace_path + "/" + name) == []
