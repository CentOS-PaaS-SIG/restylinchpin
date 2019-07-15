from __future__ import absolute_import
from tinydb import TinyDB, Query
from data_access_layer.UserBaseDB import UserBaseDB
from typing import List
from typing import Dict


class UserRestDB(UserBaseDB):

    def __init__(self, path):
        self.db = TinyDB(path)

    def db_insert(self, username, password_hash, api_key) -> None:
        """
            Inserts a workspace with id, name and status to the db
            :param username: uername for the user
            :param password_hash: hashed password for user account authentication
        """
        self.db.insert({'username': username, 'password': password_hash, 'api_key':api_key})

    def db_search_name(self, username) -> List[Dict]:
        """
            Searches a workspace record in db
            :param param: username of the user to be searched
            :return: a list of records in db that match name with param username
        """
        user = Query()
        return self.db.search(user.username == username)

    def db_list_all(self) -> List[Dict]:
        """
            Lists all user records in database
            :return: a list of all records in db
        """
        return self.db.all()

    def db_get(self, username):
        user = Query()
        return self.db.get(user.username == username)

    def db_get_api_key(self, api_key):
        user = Query()
        return self.db.get(user.api_key == api_key)

    def db_remove(self, username) -> None:
        user = Query()
        self.db.remove(user.username == username)

    def db_update(self, username, api_key) -> None:
        user = Query()
        self.db.update({'api_key': api_key}, user.username == username)

    def get_api_key(self, username):
        user = Query()
        if self.db.search(user.username == username):
            return user.api_key


