import io
import json
import unittest
import uuid
from unittest.mock import patch
from urllib.error import HTTPError

from tools.verify_fabric_connection import verify_connection


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.workspace = str(uuid.uuid4())

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output")
    def test_reads_only_expected_workspace(self, get_token, open_url):
        get_token.return_value = "test-token\n"
        open_url.return_value.__enter__.return_value = io.StringIO(
            json.dumps({"id": self.workspace})
        )
        with patch("builtins.print") as output:
            verify_connection(self.workspace)
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(
            request.full_url,
            f"https://api.fabric.microsoft.com/v1/workspaces/{self.workspace}",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertNotIn("test-token", str(output.call_args))
        self.assertNotIn(self.workspace, str(output.call_args))

    @patch("tools.verify_fabric_connection.subprocess.check_output")
    def test_rejects_invalid_or_example_config_before_auth(self, get_token):
        for value in ("", "not-a-guid", "00000000-0000-4000-8000-000000000001"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verify_connection(value)
        get_token.assert_not_called()

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="")
    def test_empty_token_is_an_error(self, get_token, open_url):
        with self.assertRaisesRegex(RuntimeError, "empty"):
            verify_connection(self.workspace)
        open_url.assert_not_called()

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="test-token")
    def test_permission_failure_is_explicit(self, get_token, open_url):
        open_url.side_effect = HTTPError("https://example.invalid", 403, "Forbidden", {}, None)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            verify_connection(self.workspace)

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="test-token")
    def test_wrong_workspace_is_an_error(self, get_token, open_url):
        open_url.return_value.__enter__.return_value = io.StringIO(
            json.dumps({"id": str(uuid.uuid4())})
        )
        with self.assertRaisesRegex(RuntimeError, "unexpected workspace"):
            verify_connection(self.workspace)


if __name__ == "__main__":
    unittest.main()
