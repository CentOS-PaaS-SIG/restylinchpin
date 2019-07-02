from __future__ import absolute_import
from tinydb import TinyDB, Query
import app
from dal.BaseDB import BaseDB
from typing import List
from typing import Dict


class RestDB(BaseDB):
    db = TinyDB(app.DB_PATH)

    def db_insert(self, identity, name, status) -> None:
        """
            Inserts a workspace with id, name and wid to the db
            :param name: name of the workspace to be inserted in db
            :param identity: unique uuid_name assigned to the workspace
            :param status: field specifying workspace creation inserted in db
        """
        self.db.insert({'id': str(identity), 'name': name, 'status': status})

    def db_remove(self, identity) -> None:
        """
            Removes a workspace record from db
            :param identity: unique uuid_name assigned to the workspace
        """
        workspace = Query()
        self.db.remove(workspace.id == identity)

    def db_update(self, identity, status) -> None:
        """
            Removes a workspace record from db
            :param identity: unique uuid_name assigned to the workspace
            :param status: field specifying workspace creation inserted in db
        """
        workspace = Query()
        self.db.update({'status': status}, workspace.id == identity)

    def db_search(self, name) -> List[Dict]:
        """
            Removes a workspace record from db
            :param name: name of the workspace to be inserted in db
            :return: a list of records in db that match name with param name
        """
        workspace = Query()
        return self.db.search(workspace.name == name)

    def db_list_all(self) -> List[Dict]:
        """
            Lists all workspace records in database
            :return: a list of all records in db
        """
        return self.db.all()


