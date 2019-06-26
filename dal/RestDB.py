from tinydb import TinyDB, Query
db = TinyDB('db.json')

class (TinyDB):
def db_insert(identity, name):
    """
        Inserts a workspace with id, name and wid to the db
        :param name: name of the workspace to be inserted in db
        :param identity: unique uuid assigned to the workspace
    """
    db.insert({'id': str(identity), 'name': name})
    return identity


def db_remove(identity) -> None:
    """
        Removes a workspace record from db
        :param identity: unique uuid assigned to the workspace
    """
    workspace = Query()
    db.remove(workspace.id == identity)


def db_update(identity, status) -> None:
    workspace = Query()
    db.update({'status': status}, workspace.id == identity)


def db_search(name):
    workspace = Query()
    return db.search(workspace.name == name)


def db_list_all():
    return db.all()

