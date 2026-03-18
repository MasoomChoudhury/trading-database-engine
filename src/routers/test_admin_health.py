import unittest
import os
import json
import time
from unittest.mock import patch, MagicMock

import sys
sys.path.append(os.path.join(os.getcwd(), 'src'))

# Simple test for check_ws_health in src/routers/admin.py
from routers.admin import check_ws_health

class TestAdminHealth(unittest.TestCase):
    def setUp(self):
        self.status_file = "ws_status.json"
        if os.path.exists(self.status_file):
            os.remove(self.status_file)

    def tearDown(self):
        if os.path.exists(self.status_file):
            os.remove(self.status_file)

    def test_check_ws_health_no_file(self):
        self.assertEqual(check_ws_health(), "Not Started")

    def test_check_ws_health_active(self):
        with open(self.status_file, "w") as f:
            json.dump({"last_heartbeat": time.time(), "is_running": True}, f)
        self.assertEqual(check_ws_health(), "Active")

    def test_check_ws_health_stalled(self):
        # Heartbeat 60 seconds ago
        with open(self.status_file, "w") as f:
            json.dump({"last_heartbeat": time.time() - 60, "is_running": True}, f)
        self.assertEqual(check_ws_health(), "Stalled")

    def test_check_ws_health_stopped(self):
        with open(self.status_file, "w") as f:
            json.dump({"last_heartbeat": time.time(), "is_running": False}, f)
        self.assertEqual(check_ws_health(), "Stopped")

if __name__ == '__main__':
    unittest.main()
