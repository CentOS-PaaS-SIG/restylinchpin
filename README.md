# restylinchpin
flask based RESTful API wrapper built around project linchpin

# Table Of Contents
- [Overview](#overview)
- [Deployment](#deployment)
- [Documenation (In progress)](#documentation)

# Overview
HTTP RESTful API.

Requests pass data via JSON encoded bodies except for GET requests where data will be passed via URL and excecute them on linchpin Command Line Interface to provision workspaces and return a JSON response to the user.

A user can currently make use of following supported features:
- <b> Create Workspaces :</b> Users can create a new worskpace locally.
- <b> List Workspaces :</b> Users can list all existing workspace within a config directory.
- <b> Delete Workspaces :</b> Users can delete workspace by name.
- <b> Fetch Workspaces from a remote URL :</b> Users can fetch remote workspaces from git or web directory locally.

## Linchpin Project
LinchPin is a simple cloud orchestration tool. Its intended purpose is managing cloud resources across multiple infrastructures. These resources can be provisioned, decommissioned, and configured all using declarative data and a simple command-line interface.

Refer to Linchpin Repository for detailed information: 
<a>https://github.com/CentOS-PaaS-SIG/linchpin</a>

# Deployment
restylinchpin will be deployed and available on Openshift.

# Documenation (In progress)
Swagger <br>
ReadTheDocs
