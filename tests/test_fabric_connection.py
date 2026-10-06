import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tools.verify_fabric_connection import verify_connection

NAMES = ["Unily-Data-Dev", "Unily-Analytics-Dev", "Unily-Vault-Dev"]


def page(names, next_url=None):
    body = {"value": [{"displayName": n, "id": f"id-{i}"} for i, n in enumerate(names)]}
    if next_url:
        body["continuationUri"] = next_url
    return io.StringIO(json.dumps(body))


class ConnectionTests(unittest.TestCase):
    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="test-token\n")
    def test_lists_workspaces_read_only_across_pages(self, get_token, open_url):
        next_url = "https://api.fabric.microsoft.com/v1/workspaces?continuationToken=x"
        open_url.return_value.__enter__.side_effect = [page(NAMES[:1], next_url), page(NAMES[1:])]
        with patch("builtins.print") as output:
            verify_connection("dev")
        first = open_url.call_args_list[0].args[0]
        self.assertEqual(first.get_method(), "GET")
        self.assertEqual(first.full_url, "https://api.fabric.microsoft.com/v1/workspaces")
        self.assertEqual(first.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(open_url.call_args_list[1].args[0].full_url, next_url)
        self.assertNotIn("test-token", str(output.call_args))
        self.assertNotIn("id-", str(output.call_args))

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="test-token")
    def test_missing_or_duplicate_workspace_is_an_error(self, get_token, open_url):
        for names in (NAMES[:2], NAMES + NAMES[:1]):
            with self.subTest(names=names):
                open_url.return_value.__enter__.side_effect = [page(names)]
                with self.assertRaisesRegex(RuntimeError, "missing, ambiguous"):
                    verify_connection("dev")

    @patch("tools.verify_fabric_connection.subprocess.check_output")
    def test_unknown_environment_fails_before_auth(self, get_token):
        with self.assertRaises(ValueError):
            verify_connection("staging")
        get_token.assert_not_called()

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="")
    def test_empty_token_is_an_error(self, get_token, open_url):
        with self.assertRaisesRegex(RuntimeError, "empty"):
            verify_connection("dev")
        open_url.assert_not_called()

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="test-token")
    def test_permission_failure_is_explicit(self, get_token, open_url):
        open_url.side_effect = HTTPError("https://example.invalid", 403, "Forbidden", {}, None)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            verify_connection("dev")

    @patch("tools.verify_fabric_connection.urlopen")
    @patch("tools.verify_fabric_connection.subprocess.check_output", return_value="test-token")
    def test_foreign_continuation_origin_is_refused(self, get_token, open_url):
        open_url.return_value.__enter__.side_effect = [page(NAMES[:1], "https://evil.example/v1/workspaces")]
        with self.assertRaisesRegex(RuntimeError, "unexpected API origin"):
            verify_connection("dev")


if __name__ == "__main__":
    unittest.main()
