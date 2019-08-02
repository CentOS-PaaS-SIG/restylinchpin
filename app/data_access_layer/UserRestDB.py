from __future__ import absolute_import
from tinydb import TinyDB, Query
from app.data_access_layer.UserBaseDB import UserBaseDB
from typing import List
from typing import Dict
from tinydb.operations import delete


class UserRestDB(UserBaseDB):

    def __init__(self, path):
        self.db = TinyDB(path)
        self.table = self.db.table('Users')

    def db_insert(self, username, password_hash, api_key_hash,
                  email, admin) -> None:
        """
            Inserts a workspace with id, name and status to the db
            :param username: username for the user
            :param password_hash: hashed password for user account
             authentication
            :param api_key_hash: hashed api_key for user token generation
            :param admin: Boolean value indicating user access rights as
             admin user
            :param email: User email
        """
        creds_folder = None
        self.table.insert({'username': username, 'password': password_hash,
                           'api_key': api_key_hash,
                           'email': email, 'admin': admin,
                           'creds_folder': creds_folder})

    def db_search_name(self, username) -> List[Dict]:
        """
            Searches a workspace record in db
            :param username: username of the user to be searched
            :return: a list of records in db that match name with
            param username
        """
        user = Query()
        return self.table.search(user.username == username)[0]

    def db_list_all(self) -> List[Dict]:
        """
            Lists all user records in database
            :return: a list of all records in db
        """
        return self.table.all()

    def db_get_username(self, username) -> List[Dict]:
        """
            Gets a user record that matches the username
            :param username: username of the user record to be searched
            :return: a matching record in db
        """
        user = Query()
        return self.table.get(user.username == username)

    def db_get_api_key(self, api_key) -> List[Dict]:
        """
            Gets a user record that matches the api_key
            :param api_key: api_key to be matched
            :return: a matching record in db
        """
        user = Query()
        return self.table.get(user.api_key == api_key)

    def db_remove(self, username) -> None:
        """
            Removes the user record that matches the username
            :param username: username of the user record
        """
        user = Query()
        self.table.remove(user.username == username)

    def db_remove_api_key(self, api_key) -> None:
        """
            Removes the api_key field from user record
            :param api_key: api_key to be deleted
        """
        user = Query()
        self.table.update(delete('api_key'), user.api_key == api_key)

    def db_reset_api_key(self, username, new_api_key) -> None:
        """
            Resets the api_key field in user record matching username
            :param new_api_key: new value of api_key
            :param username: username of the user record to be matched

        """
        user = Query()
        self.table.update({'api_key': new_api_key},
                          user.username == username)

    def db_update_admin(self, username, admin) -> None:
        """
            Updates the admin value of a user record
            :param username: username of the user record to be matched
            :param admin: boolean value to be updated, set to true
        """
        user = Query()
        self.table.update({'admin': admin}, user.username == username)

    def db_update(self, username, updated_username, password_hash,
                  email) -> None:
        """
            Updates a user's username, password, email params
            :param username: username of the user record to be updated
            :param updated_username: username for the user
            :param password_hash: hashed password for user account
            authentication
            :param email: User email
        """
        user = Query()
        self.table.update({'username': updated_username,
                           'password': password_hash,
                           'email': email}, user.username == username)

    def db_update_creds_folder(self, username, creds_folder):
        user = Query()
        self.table.update({'creds_folder': creds_folder},
                          user.username == username)
