"""Per-language AST capability behavior."""

import uidetox.analyzer_ast as analyzer_ast


def test_ast_capabilities_are_visible_and_extension_specific():
    capabilities = analyzer_ast.ast_capabilities()

    assert set(capabilities) == {"javascript", "typescript", "tsx", "css"}
    assert capabilities["typescript"]["extensions"] == [".ts"]
    assert capabilities["tsx"]["extensions"] == [".tsx"]
    assert analyzer_ast.has_ast_for(".TSX") is capabilities["tsx"]["available"]
    assert analyzer_ast.has_ast_for(".txt") is False


def test_missing_grammar_records_error_without_disabling_others(monkeypatch):
    original_languages = dict(analyzer_ast._AST_LANGUAGES)
    original_capabilities = {
        name: dict(capability)
        for name, capability in analyzer_ast.AST_CAPABILITIES.items()
    }
    real_import = analyzer_ast.importlib.import_module

    def import_with_missing_css(name: str):
        if name == "missing_css_grammar":
            raise ImportError("css grammar intentionally absent")
        return real_import(name)

    monkeypatch.setattr(
        analyzer_ast.importlib, "import_module", import_with_missing_css
    )
    try:
        analyzer_ast._load_grammar(
            "missing-css",
            "missing_css_grammar",
            "language",
            (".missing-css",),
        )

        capability = analyzer_ast.AST_CAPABILITIES["missing-css"]
        assert capability["available"] is False
        assert "css grammar intentionally absent" in capability["error"]
        assert (
            analyzer_ast.has_ast_for(".tsx")
            is original_capabilities["tsx"]["available"]
        )
    finally:
        analyzer_ast._AST_LANGUAGES.clear()
        analyzer_ast._AST_LANGUAGES.update(original_languages)
        analyzer_ast.AST_CAPABILITIES.clear()
        analyzer_ast.AST_CAPABILITIES.update(original_capabilities)
