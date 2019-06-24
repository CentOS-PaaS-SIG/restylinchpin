from tinydb import TinyDB, Query

db = TinyDB('db.json')


def db_insert(name) -> None:
    """
        Inserts a workspace with id, name and wid to the db
        :param name: name of the workspace to be inserted in db
    """
    count = len(db)
    if count == 0:
        identity = 1
    else:
        array = db.all()
        dictionary = array[count-1]
        identity = dictionary['id'] + 1
    db.insert({'id': identity, 'name': name, 'wid': name+str(identity)})


def db_remove(name) -> None:
    """
        Removes a workspace record from db
        :param name: name of the workspace to be removed from db
    """
    workspace = Query()
    db.remove(workspace.name == name)

