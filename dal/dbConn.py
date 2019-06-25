from tinydb import TinyDB, Query
import uuid
db = TinyDB('db.json')


def db_insert(identity, name):
    """
        Inserts a workspace with id, name and wid to the db
        :param name: name of the workspace to be inserted in db
        :param identity: unique uuid assigned to the workspace
    """
    db.insert({'id': str(identity), 'name': name})
    return identity


def db_remove(name) -> None:
    """
        Removes a workspace record from db
        :param name: name of the workspace to be removed from db
    """
    workspace = Query()
    db.remove(workspace.name == name)

