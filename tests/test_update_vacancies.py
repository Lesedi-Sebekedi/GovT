import unittest
from datetime import date

from scripts.update_vacancies import (
    extract_title,
    find_circular_links,
    find_pdf_links,
    get_date,
    identify_department,
    parse_pdf,
)


class VacancyParserTests(unittest.TestCase):
    def test_finds_circular_links_and_orders_newest_first(self):
        markup = """
        <a href="/newsroom/psvc/circular-34-of-2026/">Circular 34 of 2026</a>
        <a href="/newsroom/psvc/circular-2-of-2025/">Circular 2 of 2025</a>
        <a href="/newsroom/psvc/circular-35-of-2026/">Circular 35 of 2026</a>
        """
        circles = find_circular_links(markup)
        self.assertEqual((circles[0][2], circles[0][3]), (2026, 35))
        self.assertEqual(len(circles), 3)

    def test_excludes_the_combined_pdf_and_finds_department_advertisements(self):
        markup = """
        <a href="/full/circular-35.pdf">Circular 35 (click here to view the full document)</a>
        <a href="/parts/north-west.pdf">North West</a>
        """
        links = find_pdf_links(markup, "https://www.dpsa.gov.za/circular/")
        self.assertEqual(links, [("North West", "https://www.dpsa.gov.za/parts/north-west.pdf")])

    def test_reads_dates_and_provincial_department_names(self):
        self.assertEqual(get_date("Posting Date: 2 October 2026"), date(2026, 10, 2))
        self.assertEqual(get_date("Closing Date: 28 September 026", 2026), date(2026, 9, 28))
        self.assertIsNone(get_date("Closing Date: 28 September 026"))
        department, province = identify_department(
            "PROVINCIAL ADMINISTRATION: NORTH WEST\n"
            "DEPARTMENT OF COMMUNITY SAFETY AND TRANSPORT MANAGEMENT\n"
            "APPLICATIONS\n",
            "North West",
        )
        self.assertEqual(department, "Department of Community Safety And Transport Management")
        self.assertEqual(province, "North West")

    def test_extracts_post_title_without_reference_number(self):
        block = """
        :
        ASSISTANT DIRECTOR: DEMAND MANAGEMENT REF NO: 38/2026/2027

        Directorate: Supply Chain Management

        SALARY
        :
        R487 197 per annum (Level 09)
        """
        self.assertEqual(extract_title(block), "ASSISTANT DIRECTOR: DEMAND MANAGEMENT")

    def test_parses_realistic_single_post_pdf(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF is installed from requirements.txt in CI")

        import io

        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(
            fitz.Rect(40, 40, 550, 790),
            "PROVINCIAL ADMINISTRATION: NORTH WEST\n"
            "DEPARTMENT OF COMMUNITY SAFETY AND TRANSPORT MANAGEMENT\n"
            "APPLICATIONS\n"
            "CLOSING DATE\n:\n16 October 2026 at 15H30\n"
            "POST 35/231\n:\nASSISTANT DIRECTOR: DEMAND MANAGEMENT REF NO: 38/2026/2027\n"
            "Directorate: Supply Chain Management\n"
            "SALARY\n:\nR487 197 per annum (Level 09)\n"
            "CENTRE\n:\nHead Office\n"
            "REQUIREMENTS\n:\nMatric/Grade 12 and a relevant degree.\n"
            "DUTIES\n:\nManage procurement and compile reports.\n",
            fontsize=9,
        )
        pdf_bytes = doc.tobytes()
        doc.close()
        records = parse_pdf(
            pdf_bytes,
            "Circular 35 of 2026",
            date(2026, 10, 2),
            "North West",
            "https://example.gov.za/north-west.pdf",
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "ASSISTANT DIRECTOR: DEMAND MANAGEMENT")
        self.assertEqual(records[0]["closingDate"], "2026-10-16")
        self.assertEqual(records[0]["province"], "North West")
        self.assertEqual(records[0]["reference"], "38/2026/2027")
        self.assertEqual(records[0]["location"], "Head Office")


if __name__ == "__main__":
    unittest.main()
