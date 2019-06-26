from abc import ABC, abstractmethod


class tinyDb(ABC):

    @abstractmethod
    def get(self, index):
        pass

    @abstractmethod
    def insert(self, data):
        pass

def get_database():
    """call this anywhere I need a concrete database class"""
    return Database.__subclasses__()[-1]