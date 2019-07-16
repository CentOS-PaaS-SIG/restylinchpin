from __future__ import absolute_import
from tinydb import TinyDB, Query
from data_access_layer.UserBaseDB import UserBaseDB
from typing import List
from typing import Dict
from tinydb.operations import delete


class UserRestDB(UserBaseDB):

    def __init__(self, path):
        self.db = TinyDB(path)

    def db_insert(self, username, password_hash, api_key_hash, email, admin) -> None:
        """
            Inserts a workspace with id, name and status to the db
            :param username: username for the user
            :param password_hash: hashed password for user account authentication
            :param api_key_hash: hashed api_key for user token generation
            :param admin: Boolean value indicating user access rights as admin user
            :param email: User email
        """
        self.db.insert({'username': username, 'password': password_hash, 'api_key': api_key_hash,
                        'email': email, 'admin': admin})

    def db_search_name(self, username) -> List[Dict]:
        """
            Searches a workspace record in db
            :param username: username of the user to be searched
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

    def db_get_username(self, username):
        user = Query()
        return self.db.get(user.username == username)

    def db_get_api_key(self, api_key):
        user = Query()
        return self.db.get(user.api_key == api_key)

    def db_remove(self, username) -> None:
        user = Query()
        self.db.remove(user.username == username)

    def db_remove_api_key(self, api_key) -> None:
        user = Query()
        self.db.update(delete('api_key'), user.api_key == api_key)

    def db_reset_api_key(self, username, new_api_key) -> None:
        user = Query()
        self.db.update({'api_key': new_api_key}, user.username == username)

    def db_update_admin(self, username, admin) -> None:
        user = Query()
        self.db.update({'admin': admin}, user.username == username)

    def db_update(self, username,  updated_username, password_hash, email) -> None:
        """
            Inserts a workspace with id, name and status to the db
            :param updated_username: username for the user
            :param password_hash: hashed password for user account authentication
            :param email: User email
        """
        user = Query()
        self.db.update({'username': updated_username, 'password': password_hash,
                        'email': email}, user.username == username)
