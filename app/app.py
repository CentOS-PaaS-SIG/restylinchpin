from flask import Flask, jsonify, request, Response
import subprocess
import os
import yaml

app = Flask(__name__)

# Reading directory path from config.json file

with open('config.yml', 'r') as f:
    doc = yaml.load(f)

WORKING_DIR = doc['working_path']

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
        print(e)
        return jsonify(status=409, code=output.returncode)


@app.route('/workspace/delete', methods=['POST'])
def linchpin_delete_workspace():
    try:
        data = request.json  # Get request body
        name = data["name"]
        # path specifying location of working directory inside server
        for x in os.listdir(os.path.join(app.root_path)):
            if x == name:
                output = subprocess.Popen(["rm", "-r", os.path.join(app.root_path + WORKING_DIR + name)]
                                          , stdout=subprocess.PIPE)
                return jsonify(name=name, status="Workspace deleted successfully", Code=output.returncode)
        return jsonify(status="Workspace " + name + " not found")
    except Exception as e:
        print(e)
        return jsonify(status=409, code=output.returncode)


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)






