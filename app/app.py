from flask import Flask, jsonify, request, Response
from flask_swagger_ui import get_swaggerui_blueprint
from flask_cors import CORS,cross_origin
import subprocess
import os
import yaml
import json

app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

with open('config.yml', 'r') as f:
    doc = yaml.load(f)

with open('swagger.json', 'r') as f:
    jsonData = json.load(f)


# Register blueprint at URL
# (URL must match the one given to factory function above)
SWAGGER_URL = '/api/docs'  # URL for exposing Swagger UI (without trailing '/')
API_URL = 'https://api.myjson.com/bins/m95ah'  # Our API url (can of course be a local resource)

# Call factory function to create our blueprint
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,  # Swagger UI static files will be mapped to '{SWAGGER_URL}/dist/'
    API_URL,
    config={  # Swagger UI config overrides
        'app_name': "Test application"
    }
)

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


if __name__ == "__main__":
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
    app.run(host='0.0.0.0', debug=True)






