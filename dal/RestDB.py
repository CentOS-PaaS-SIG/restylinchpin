from __future__ import absolute_import
from tinydb import TinyDB, Query
from dal.Tiny import Tiny


class RestDB(Tiny):
    db = TinyDB('db.json')

    def db_insert(self, identity, name, status):
        """
            Inserts a workspace with id, name and wid to the db
            :param name: name of the workspace to be inserted in db
            :param identity: unique uuid assigned to the workspace
            :param status: field specifying workspace creation inserted in db
        """
        self.db.insert({'id': str(identity), 'name': name, 'status': status})
        return identity

    def db_remove(self, identity) -> None:
        """
            Removes a workspace record from db
            :param identity: unique uuid assigned to the workspace
        """
        workspace = Query()
        self.db.remove(workspace.id == identity)

    def db_update(self, identity, status) -> None:
        """
            Removes a workspace record from db
            :param identity: unique uuid assigned to the workspace
            :param status: field specifying workspace creation inserted in db
        """
        workspace = Query()
        self.db.update({'status': status}, workspace.id == identity)

    def db_search(self, name):
        """
            Removes a workspace record from db
            :param name: name of the workspace to be inserted in db
        """
        workspace = Query()
        return self.db.search(workspace.name == name)

    def db_list_all(self):
        """
            Lists all workspace records in database
        """
        return self.db.all()


