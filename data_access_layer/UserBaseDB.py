from abc import ABC, abstractmethod


class UserBaseDB(ABC):

    @abstractmethod
    def db_insert(self, username, password_hash, api_key, admin):
        return

    @abstractmethod
    def db_search_name(self, username):
        return

    @abstractmethod
    def db_list_all(self):
        pass

    @abstractmethod
    def db_get_username(self, username):
        pass

    @abstractmethod
    def db_get_api_key(self, api_key):
        pass

    @abstractmethod
    def db_remove(self, username):
        pass

    @abstractmethod
    def db_update(self, username, api_key):
        pass

    @abstractmethod
    def db_update_admin(self, username, admin):
        pass
