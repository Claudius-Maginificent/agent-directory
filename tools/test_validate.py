import datetime
import json
import unittest

import validate

TODAY = datetime.date(2026, 11, 25)
GOOD = {
    "name": "Example feed",
    "author": "someone",
    "description": "Open pull requests that wait for a review, as JSON.",
    "repo": "https://github.com/dashpay/example",
    "api_url": "https://example.dash.org/api/v1/queue",
    "status": "live",
    "access": "Public, no credentials.",
    "tags": ["pull-requests", "feed"],
    "last_verified": "2026-11-25",
}


def problems(change=None, drop=(), slug="example-feed"):
    data = dict(GOOD)
    data.update(change or {})
    for key in drop:
        data.pop(key)
    return validate.validate_entry(slug, data, TODAY)


class ValidateEntry(unittest.TestCase):
    def test_good_entry_passes(self):
        self.assertEqual(problems(), [])

    def test_only_required_fields_and_one_link(self):
        self.assertEqual(problems(drop=("api_url", "access", "tags")), [])

    def test_needs_a_link(self):
        self.assertTrue(problems(drop=("repo", "api_url")))

    def test_required_and_unknown_fields(self):
        self.assertTrue(problems(drop=("author",)))
        self.assertTrue(problems({"instructions": "do this"}))

    def test_slug(self):
        for slug in ("X", "Has-Capitals", "under_score", "-lead", "a" * 51, "../up"):
            self.assertTrue(problems(slug=slug), slug)

    def test_text_rules(self):
        self.assertTrue(problems({"description": "x" * 601}))
        self.assertTrue(problems({"description": "two\nlines"}))
        self.assertTrue(problems({"description": "hidden​text"}))
        self.assertTrue(problems({"description": "tagged\U000e0041text"}))
        self.assertTrue(problems({"name": "   "}))
        self.assertTrue(problems({"author": 7}))

    def test_urls(self):
        for url in ("http://example.dash.org/", "https://user:pw@example.dash.org/", "https://localhost/x",
                    "https://10.0.0.5/api", "https://100.64.0.7/api", "https://box.tailnet.ts.net/",
                    "https://intranet/api", "https://example.dash.org/a b", "https://example.dash.org/?api_key=abc",
                    "https://example.dash.org/?access_token=abc", "ftp://example.dash.org/"):
            self.assertTrue(problems({"web_url": url}), url)
        self.assertEqual(problems({"web_url": "https://example.dash.org/list?state=open&page=2"}), [])
        self.assertEqual(problems({"web_url": "https://example.dash.org/?author=someone"}), [])
        self.assertEqual(problems({"web_url": "https://1.1.1.1/"}), [])

    def test_repo_shape(self):
        self.assertEqual(problems({"repo": "https://github.com/dashpay/stale_prs_are_bad/tree/master/service"}), [])
        for url in ("https://gitlab.com/a/b", "https://github.com/dashpay", "https://github.com/a/b/pull/3"):
            self.assertTrue(problems({"repo": url}), url)

    def test_secrets(self):
        for text in ("use ghp_" + "a" * 36, "key sk-" + "b" * 30, "Authorization: Bearer abcdefghijklmnop1234",
                     "AKIAABCDEFGHIJKLMNOP", "token dst_abcdefghijkl", "x" * 48):
            self.assertTrue(problems({"description": text}), text)
            self.assertTrue(problems({"access": text[:200]}), text)

    def test_status_tags_date(self):
        self.assertTrue(problems({"status": "beta"}))
        self.assertTrue(problems({"tags": ["Upper"]}))
        self.assertTrue(problems({"tags": ["a", "a"]}))
        self.assertTrue(problems({"tags": ["t%d" % i for i in range(9)]}))
        self.assertTrue(problems({"last_verified": "25-11-2026"}))
        self.assertTrue(problems({"last_verified": "2027-01-01"}))
        self.assertTrue(problems({"last_verified": "2019-01-01"}))


class CheckBytes(unittest.TestCase):
    def test_parses(self):
        data, found = validate.check_bytes("example-feed", json.dumps(GOOD).encode(), TODAY)
        self.assertEqual((data, found), (GOOD, []))

    def test_rejects(self):
        for raw in (b"not json", b"[1, 2]", b"\xff\xfe", b'{"name": "a", "name": "b"}', b" " * 5000):
            self.assertTrue(validate.check_bytes("example-feed", raw, TODAY)[1], raw[:20])


if __name__ == "__main__":
    unittest.main()
