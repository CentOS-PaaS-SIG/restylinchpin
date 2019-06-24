from tinydb import TinyDB, Query

db = TinyDB('db.json')


def db_insert(name):
    count = len(db)
    if count == 0:
        identity = 1
    else:
        array = db.all()
        dictionary = array[count-1]
        identity = dictionary['id'] + 1
    db.insert({'id': identity, 'name': name, 'wid': name+str(identity)})


def db_remove(name):
    workspace = Query()
    db.remove(workspace.name == name)
