import unittest
import app
from app.data_access_layer import RestDB
from app.data_access_layer import UserRestDB

BASE_URL = 'http://localhost:5000/api/v1.0'


class UnitTest(unittest.TestCase):

    def setUp(self):
        self.app = app.app.test_client()
        self.app.testing = True

    def test_db_create_admin_user(self):
        app.create_admin_user(app.DB_PATH, app.ADMIN_USERNAME,
                              app.ADMIN_PASSWORD, app.ADMIN_EMAIL)
        self.assertEqual("admin", app.get_connection_users(app.DB_PATH).db_search_name("admin")['username'])

    def test_get_connection(self):
        self.assertIsInstance(app.get_connection(app.DB_PATH), RestDB.RestDB)

    def test_get_connection_users(self):
        self.assertIsInstance(app.get_connection_users(app.DB_PATH), UserRestDB.UserRestDB)

    def test_create_fetch_cmd(self):
        data = {"name": "test", "url": "www.github.com/CentOS-PaaS-SIG/linchpin",
                "rootfolder":"/"}
        identity = "test123"
        self.assertEqual(app.create_fetch_cmd(data, identity, app.WORKSPACE_DIR),
                         ["linchpin", "-w " + app.WORKSPACE_DIR + identity, "fetch", "--root", data['rootfolder'],
                          data['url']])

    def test_create_cmd_workspace(self):
        data = {"id": "test123",
                "provision_type": "workspace",
                "pinfile_path": "/dummy/"
                }
        action = "up"
        self.assertEqual(app.create_cmd_workspace(data, data['id'], action,
                         app.WORKSPACE_PATH, app.WORKSPACE_DIR,
                         app.CREDS_PATH), ["linchpin", "-w " + app.WORKSPACE_DIR + data['id'] + data['pinfile_path'],
                                           "--creds-path", "/", "up"])

    def test_create_cmd_up_pinfile(self):
        data = {"id": "UnitTest",
                "provision_type": "pinfile",
                "pinfile_content":{"test":"pinfile_data"}}
        self.assertEqual(app.create_cmd_up_pinfile(data, data['id'], app.WORKSPACE_DIR, app.CREDS_PATH),
                         ["linchpin", "-w " + app.WORKSPACE_DIR + data['id'] + "/dummy", "-p" +
                          "PinFile.json", "--creds-path", "/", "up"])


if __name__ == '__main__':
    unittest.main()
