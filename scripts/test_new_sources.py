"""Offline regressionstest af datobetydning, robotsregler og kaldeloft.

Små testeksempler følger de observerede felter. De publiceres aldrig som tilbud.
"""
import copy
import json
import unittest
import urllib.error
from unittest.mock import patch

from common import ROOT
from source_reader import SourceReader, robot_allows, robot_rules
from sources import indiecampers, touringcars, watchpages


WINDOW = json.loads((ROOT / "data.json").read_text())["window"]


def indie_props(page=1, total_pages=1):
    return {"serverQuery": {"page": page}, "cityNames": {"berlin-offers": "Berlin", "paris": "Paris"},
            "vanCards": {}, "initialSearch": {"kind": "loaded",
            "pagination": {"page": page, "total_pages": total_pages},
            "results": {"listings": [{"pick_up_location": "berlin-offers", "drop_off_location": "paris",
                "deals": [{"van_category": "camper", "date_range": {
                    "earliest_checkin": "2026-12-26", "latest_checkout": "2027-01-08"},
                    "price_range": {"min": 4.6}, "max_nights": 7}]}]}}}


def indie_html(props):
    stream = "97:" + json.dumps(["$", "$L99", None, props]) + "\n"
    # React må dele JSON-strømmen mellem flere script-tags.
    return "".join('<script>self.__next_f.push(' + json.dumps([1, part]) + ')</script>'
                   for part in (stream[:25], stream[25:]))


TOURING = '''<div class="flash-deal-card reveal" data-deal-id="1"
 data-deal-url="https://www.touringcars.com/en/flash-deals/example/"
 data-pickup-location="Oslo, Norway" data-return-location="Helsinki, Finland"
 data-date-start="2026-12-26" data-date-end="2027-01-04" data-currency="EUR">
 <div><span class="deal-price">29 <span>€</span><small>/day</small></span></div></div>'''


class SourceTests(unittest.TestCase):
    def test_robots_combines_wildcard_groups_and_honours_allow(self):
        rules = robot_rules('User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n'
                            '\nUser-agent: *\nDisallow: /*?\nAllow: /deals?page=2$\n')
        self.assertTrue(robot_allows(rules, 'https://example.org/deals'))
        self.assertFalse(robot_allows(rules, 'https://example.org/deals?page=1'))
        self.assertTrue(robot_allows(rules, 'https://example.org/deals?page=2'))
        self.assertFalse(robot_allows(rules, 'https://example.org/deals?page=2&x=3'))

    def test_robots_blocks_before_page_request(self):
        reader = SourceReader(pause=0)
        with patch.object(reader, '_raw', return_value='User-agent: *\nDisallow: /api/') as raw:
            with self.assertRaises(PermissionError):
                reader.read('https://example.org/api/deals')
            self.assertEqual(raw.call_count, 1)

    def test_hard_request_budget(self):
        reader = SourceReader(max_calls=0, pause=0)
        with self.assertRaises(RuntimeError):
            reader.read('https://example.org/')
        self.assertEqual(reader.calls, 0)

    def test_robots_403_stops_and_404_allows(self):
        for status in (403, 404):
            reader = SourceReader(pause=0)
            error = urllib.error.HTTPError('https://example.org/robots.txt', status, '', {}, None)
            with patch.object(reader, '_raw', side_effect=[error, 'offers']) as raw:
                if status == 403:
                    with self.assertRaises(urllib.error.HTTPError):
                        reader.read('https://example.org/deals')
                    self.assertEqual(raw.call_count, 1)
                else:
                    self.assertEqual(reader.read('https://example.org/deals'), 'offers')

    def test_robots_challenge_is_not_permission(self):
        reader = SourceReader(pause=0)
        with patch.object(reader, '_raw', return_value='<html>Challenge</html>') as raw:
            with self.assertRaises(ValueError):
                reader.read('https://example.org/deals')
            self.assertEqual(raw.call_count, 1)

    def test_connection_retry_but_never_access_retry(self):
        for error in (urllib.error.URLError('connection reset'),
                      urllib.error.HTTPError('https://example.org/deals', 403, '', {}, None)):
            reader = SourceReader(pause=0)
            with patch.object(reader, '_raw', side_effect=['User-agent: *\nAllow: /', error, 'offers']) as raw:
                if isinstance(error, urllib.error.HTTPError):
                    with self.assertRaises(urllib.error.HTTPError):
                        reader.read('https://example.org/deals')
                    self.assertEqual(raw.call_count, 2)
                else:
                    self.assertEqual(reader.read('https://example.org/deals'), 'offers')
                    self.assertEqual(raw.call_count, 3)

    def test_indie_split_stream_and_missing_data(self):
        self.assertEqual(indiecampers.parse(indie_html(indie_props())), indie_props())
        with self.assertRaises(ValueError):
            indiecampers.parse('<html>Challenge or changed layout</html>')

    def test_indie_checkout_is_never_used_as_last_pickup_or_currency(self):
        with patch.object(SourceReader, 'read', return_value=indie_html(indie_props())):
            deal, = indiecampers.fetch_deals(WINDOW, 'test')
        self.assertEqual(deal['availability']['from'], '2026-12-26')
        self.assertIsNone(deal['availability']['to'])
        self.assertIsNone(deal['currency'])
        self.assertIsNone(deal['pricePerDay'])
        self.assertIsNone(deal['days'])
        self.assertEqual(deal['fit'], 'nej')
        self.assertEqual(deal['availability']['state'], 'ukendt')
        self.assertNotIn('aflever', deal['yourPlan'])
        self.assertIn('2027-01-08', deal['availability']['detail'])

    def test_indie_pages_deduplicate_and_filter_both_ends(self):
        first = indie_props(total_pages=2)
        second = indie_props(page=2)
        other = copy.deepcopy(second['initialSearch']['results']['listings'][0])
        other.update(pick_up_location='paris', drop_off_location='paris')
        second['initialSearch']['results']['listings'].append(other)
        with patch.object(SourceReader, 'read', side_effect=[indie_html(first), indie_html(second)]) as read:
            deals = indiecampers.fetch_deals(WINDOW, 'test')
        self.assertEqual(len(deals), 1)
        self.assertEqual(indiecampers.LAST_OTHER, 1)
        self.assertTrue(read.call_args_list[1].args[0].endswith('?page=2'))

    def test_indie_repeated_page_fails_instead_of_publishing_empty_list(self):
        with patch.object(SourceReader, 'read', return_value=indie_html(indie_props(total_pages=2))):
            with self.assertRaises(ValueError):
                indiecampers.fetch_deals(WINDOW, 'test')

    def test_indie_caps_pages_and_reports_partial(self):
        pages = [indie_html(indie_props(page=n, total_pages=25)) for n in range(1, 20)]
        with patch.object(SourceReader, 'read', side_effect=pages) as read:
            indiecampers.fetch_deals(WINDOW, 'test')
        self.assertEqual(read.call_count, 19)  # Plus én robots.txt i en livekørsel.
        self.assertTrue(indiecampers.PARTIAL)

    def test_touring_price_countries_dedup_and_uncertain_duration(self):
        with patch.object(SourceReader, 'read', return_value=TOURING + TOURING):
            deal, = touringcars.fetch_deals(WINDOW, 'test')
        self.assertEqual(deal['pricePerDay'], 29)
        self.assertEqual(deal['pickupCountry'], 'NO')
        self.assertEqual(deal['dropoffCountry'], 'FI')
        self.assertIsNone(deal['days'])
        self.assertEqual(deal['fit'], 'nej')
        self.assertIn('stationsgebyr', deal['totalCost'])

    def test_touring_outside_zone_and_unknown_layout(self):
        with patch.object(SourceReader, 'read', return_value=TOURING.replace('Oslo, Norway', 'Tromsø, Norway')):
            self.assertEqual(touringcars.fetch_deals(WINDOW, 'test'), [])
        self.assertEqual(touringcars.LAST_OTHER, 1)
        with self.assertRaises(ValueError):
            touringcars.parse('<html>Changed layout</html>')

    def test_comment_examples_never_become_visible_deals(self):
        self.assertEqual(watchpages.visible('No deals<!-- old <b>Oslo</b> deal -->').strip(), 'No deals')


if __name__ == '__main__':
    unittest.main()
