"""Native Hancom equation-script conversion and scope regression tests."""
import sys
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.hwp_equation import EquationConversionError, latex_to_hwp
from tools.metrics import metrics
from tools import gen


class HwpEquationConversionTests(unittest.TestCase):
    def test_consecutive_variables_get_individual_grouped_subscripts(self):
        self.assertEqual(latex_to_hwp(r"P_0 V_0"),
                         "{ P _ { 0 } } { V _ { 0 } }")
        self.assertEqual(latex_to_hwp(r"P_{0}V_{0}"),
                         "{ P _ { 0 } } { V _ { 0 } }")

    def test_nested_subscript_and_superscript_keep_their_own_scopes(self):
        self.assertEqual(latex_to_hwp(r"x_{i_0}^{2}"),
                         "{ x _ { { i _ { 0 } } } ^ { 2 } }")

    def test_compound_bases_are_grouped_before_their_scripts(self):
        cases = {
            r"\frac{a}{b}_0 V_0": "{ { { a } over { b } } _ { 0 } } { V _ { 0 } }",
            r"\sqrt{x}_0 V_0": "{ { sqrt { x } } _ { 0 } } { V _ { 0 } }",
            r"\vec{F}_{net} V_0": "{ { vec { F } } _ { n e t } } { V _ { 0 } }",
            r"(a+b)^2": "{ { ( a + b ) } ^ { 2 } }",
            r"\left(a+b\right)^2": "{ { LEFT ( a + b RIGHT ) } ^ { 2 } }",
            r"\left\{x\right\}": "LEFT lbrace x RIGHT rbrace",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(latex_to_hwp(source), expected)

    def test_fraction_root_vector_greek_units_and_functions_use_hwp_commands(self):
        cases = {
            r"\dfrac{m v^2}{2}": "{ m { v ^ { 2 } } } over { 2 }",
            r"\frac12": "{ 1 } over { 2 }",
            r"\sqrt{3}": "sqrt { 3 }",
            r"\sqrt[3]{x}": "root { 3 } of { x }",
            r"\vec{F}_1": "{ { vec { F } } _ { 1 } }",
            r"\theta_0 + \Delta t": "{ theta _ { 0 } } + DELTA t",
            r"10\,\mathrm{m/s}": "10 ` rm { m/s }",
            r"\sin^2\theta + \cos\theta": "{ sin ^ { 2 } } theta + cos theta",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                converted = latex_to_hwp(source)
                self.assertEqual(converted, expected)
                self.assertNotIn("\\", converted)

    def test_literal_tilde_becomes_sim_glyph_and_spacing_commands_remain_spacing(self):
        cases = {
            "1~5": "1 ∼ 5",
            "v~t": "v ∼ t",
            r"\sim": "SIM",
            r"\~": "∼",
            r"\text{1~5}": "rm { 1∼5 }",
            r"\text{a\~b}": "rm { a∼b }",
            r"a\quad b": "a ~~ b",
            r"a\qquad b": "a ~~~~ b",
            r"a\;b": "a ~ b",
            r"a\:b": "a ~ b",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(latex_to_hwp(source), expected)

    def test_root_index_and_radicand_have_native_engine_verified_scope(self):
        self.assertEqual(latex_to_hwp(r"\sqrt[n+1]{x_0^2}"),
                         "root { n + 1 } of { { x _ { 0 } ^ { 2 } } }")
        self.assertEqual(latex_to_hwp(r"\sqrt[3]{x}_0 V_0"),
                         "{ { root { 3 } of { x } } _ { 0 } } { V _ { 0 } }")
        self.assertEqual(metrics(latex_to_hwp(r"\sqrt[3]{x}"))[1:], (1350, 80))

    def test_generated_script_elements_use_the_converter(self):
        runs = gen.runs(r"속도 $P_0 V_0$와 $\frac{1}{2}at^2$")
        scripts = [run.findtext("EQUATION/SCRIPT") for run in runs
                   if run.find("EQUATION") is not None]
        self.assertEqual(scripts, ["{ P _ { 0 } } { V _ { 0 } }",
                                   "{ 1 } over { 2 } a { t ^ { 2 } }"])
        self.assertTrue(all("\\" not in script for script in scripts))

    def test_generated_hml_normalizes_source_tildes_in_text_and_tables(self):
        record = [None] * 21
        record[1] = 1
        record[9] = r"범위 1~5, literal \~"
        record[11] = r"다음 식 $1~5$와 $v~t$, $\sim$, $\~$, $\quad$, $\qquad$, $\;$, $\:$를 보자."
        record[14] = 5
        record[20] = [{
            "kind": "table",
            "label": "표 1~5 캡션",
            "content": "|시간~속도|1~5|\n|---|---|\n|1|2|",
        }]
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            path = Path(temp_dir) / "tilde.hml"
            xml = gen.build(src=__file__, out=str(path), exam=str(ROOT),
                            title="시험 1~5", records=[record])
        self.assertEqual(record[9], r"범위 1~5, literal \~")
        self.assertIn("~", record[20][0]["content"])

        root = ET.fromstring(xml)
        char_text = "".join("".join(char.itertext()) for char in root.iter("CHAR"))
        self.assertNotIn("~", char_text)
        self.assertIn("시험 1∼5", char_text)
        self.assertIn("범위 1∼5, literal ∼", char_text)
        self.assertIn("표 1∼5 캡션", char_text)
        self.assertIn("시간∼속도", char_text)
        self.assertIn("1∼5", char_text)

        scripts = [equation.findtext("SCRIPT") for equation in root.iter("EQUATION")]
        self.assertEqual(scripts, ["1 ∼ 5", "v ∼ t", "SIM", "∼", "~~", "~~~~", "~", "~"])

    def test_existing_native_command_words_are_preserved(self):
        self.assertEqual(latex_to_hwp("rm {m/s} + DELTA over theta"),
                         "rm { m / s } + DELTA over theta")
        self.assertEqual(latex_to_hwp("vec F_1"), "vec { F _ { 1 } }")

    def test_relation_symbols_use_published_hwp_names_and_unknown_ones_fail(self):
        self.assertEqual(latex_to_hwp(r"a\parallel b + \pm c + \ldots + \vdots + \ddots"),
                         "a VERT b + PLUSMINUS c + LDOTS + VDOTS + DDOTS")
        with self.assertRaises(EquationConversionError):
            latex_to_hwp(r"\Re z")

    def test_multi_character_relations_remain_single_native_terms(self):
        self.assertEqual(latex_to_hwp("x->0,y<-1"), "x -> 0 , y <- 1")
        self.assertEqual(latex_to_hwp("x<=y, a>=b, c!=d, e==f"),
                         "x LEQ y , a GEQ b , c neq d , e EQUIV f")

    def test_metrics_use_balanced_nested_fraction_groups(self):
        nested = latex_to_hwp(r"\frac{\frac{1}{2}}{\frac{3}{4}}")
        width, height, baseline = metrics(nested)
        self.assertGreater(width, 0)
        self.assertEqual(height, 2800)
        self.assertEqual(baseline, 53)
        with_root = latex_to_hwp(r"\sqrt{\frac{a}{b}}")
        self.assertEqual(metrics(with_root)[1:], (3050, 50))

    def test_unknown_commands_and_malformed_groups_fail_explicitly(self):
        for source in (r"\unknown{x}", r"\frac{a}", r"P_{0"):
            with self.subTest(source=source):
                with self.assertRaises(EquationConversionError):
                    latex_to_hwp(source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
