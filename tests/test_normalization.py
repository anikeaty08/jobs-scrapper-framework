import unittest

from hirehunt.models import SalaryPeriod, WorkMode
from hirehunt.utils.normalization import normalize_city, parse_money, parse_work_mode


class NormalizationTests(unittest.TestCase):
    def test_city_alias(self):
        self.assertEqual(normalize_city("bangalore"), "Bengaluru")

    def test_lpa_salary(self):
        money = parse_money("5 - 8 LPA")
        self.assertEqual(money.currency, "INR")
        self.assertEqual(money.period, SalaryPeriod.YEAR)
        self.assertEqual(money.min_amount, 500000)
        self.assertEqual(money.max_amount, 800000)

    def test_monthly_stipend(self):
        money = parse_money("₹20,000 per month")
        self.assertEqual(money.currency, "INR")
        self.assertEqual(money.period, SalaryPeriod.MONTH)
        self.assertEqual(money.min_amount, 20000)

    def test_work_mode(self):
        self.assertEqual(parse_work_mode("Work from home"), WorkMode.REMOTE)


if __name__ == "__main__":
    unittest.main()
