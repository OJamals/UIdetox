import pytest
from uidetox.memory import (
    clear_memory,
    add_pattern,
    get_patterns,
    add_note,
    get_notes,
    embed_file_context,
    embed_fix_outcome,
    query_relevant_context,
    build_targeted_context
)

@pytest.fixture(autouse=True)
def clean_memory():
    """Ensure memory is clean before and after each test."""
    clear_memory()
    yield
    clear_memory()

def test_add_and_get_patterns():
    add_pattern("always use vanilla css instead of tailwind", category="styling")
    add_pattern("python variables should use snake_case", category="naming")
    
    # Check that we can retrieve everything without a query
    all_patterns = get_patterns()
    assert len(all_patterns) == 2
    assert any("vanilla css" in p["pattern"] for p in all_patterns)
    
    # Check semantic retrieval
    styled_patterns = get_patterns("how should I style things?")
    assert len(styled_patterns) > 0
    # The most relevant one should involve styling
    assert "vanilla css" in styled_patterns[0]["pattern"]

def test_add_and_get_notes():
    add_note("the user prefers dark mode by default")
    add_note("we need to review the checkout flow next")
    
    # Check retrieval
    notes = get_notes("dark mode")
    assert len(notes) > 0
    assert "dark mode" in notes[0]["note"]

def test_context_embedding_and_retrieval():
    embed_file_context("src/App.tsx", "App.tsx sets up the main Provider and routing.")
    embed_fix_outcome("src/Button.tsx", "Button has no hover state", "Added :hover to CSS", outcome="resolved")
    
    # Search across collections for routing
    res_ctx = query_relevant_context("routing setup")
    assert len(res_ctx) > 0
    
    # Check that the most relevant item is the App.tsx
    assert "routing" in res_ctx[0]["text"]
    assert res_ctx[0]["collection"] == "file_contexts"
    
    # Check that relevance mapping bug is fixed
    # The relevance should be strictly greater than 0
    assert res_ctx[0]["relevance"] > 0
    
    # Build targeted context
    targeted = build_targeted_context(["src/App.tsx", "src/Button.tsx"], issue_text="button layout is broken")
    assert "Targeted Context" in targeted
    assert "App.tsx sets up the main Provider and routing." in targeted
