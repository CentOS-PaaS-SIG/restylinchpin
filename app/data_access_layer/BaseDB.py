from abc import ABC, abstractmethod


class BaseDB(ABC):

    @abstractmethod
    def db_insert(self, identity, name, status, username):
        return

    @abstractmethod
    def db_insert_no_name(self, identity, status, username):
        return

    @abstractmethod
    def db_search(self, name, admin, username):
        return

    @abstractmethod
    def db_update(self, identity, status):
        pass

    @abstractmethod
    def db_remove(self, identity, admin, username):
        pass

    @abstractmethod
    def db_list_all(self, username, admin):
        pass

    @abstractmethod
    def db_search_username(self, username):
        pass

    @abstractmethod
    def db_search_identity(self, identity):
        pass
