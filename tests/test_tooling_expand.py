from uidetox.tooling import detect_all  # type: ignore

def test_detect_stylelint(tmp_path):
    (tmp_path / "package.json").write_text('{"devDependencies": {"stylelint": "latest"}}', encoding="utf-8")
    (tmp_path / ".stylelintrc").write_text("{}", encoding="utf-8")
    
    profile = detect_all(tmp_path)
    # Check if stylelint is in all_linters
    names = [l.name for l in profile.all_linters]
    assert "stylelint" in names
    
    stylelint = next(l for l in profile.all_linters if l.name == "stylelint")
    assert "stylelint" in stylelint.run_cmd
    assert "--fix" in stylelint.fix_cmd

def test_detect_markuplint(tmp_path):
    (tmp_path / "package.json").write_text('{"devDependencies": {"markuplint": "latest"}}', encoding="utf-8")
    (tmp_path / ".markuplintrc").write_text("{}", encoding="utf-8")
    
    profile = detect_all(tmp_path)
    names = [l.name for l in profile.all_linters]
    assert "markuplint" in names
    
    markuplint = next(l for l in profile.all_linters if l.name == "markuplint")
    assert "markuplint" in markuplint.run_cmd
    assert "--fix" in markuplint.fix_cmd

def test_multiple_linters(tmp_path):
    (tmp_path / "package.json").write_text('{"devDependencies": {"eslint": "latest", "stylelint": "latest"}}', encoding="utf-8")
    (tmp_path / ".eslintrc").write_text("{}", encoding="utf-8")
    (tmp_path / ".stylelintrc").write_text("{}", encoding="utf-8")
    
    profile = detect_all(tmp_path)
    names = [l.name for l in profile.all_linters]
    assert "eslint" in names
    assert "stylelint" in names
    assert profile.linter.name == "eslint" # primary


def test_detect_contract_artifacts_keys_always_present(tmp_path):
    profile = detect_all(tmp_path).to_dict()
    artifacts = profile.get("contract_artifacts")
    assert isinstance(artifacts, dict)
    assert artifacts.get("schema_files") == []
    assert artifacts.get("dto_files") == []
    assert artifacts.get("contract_files") == []


def test_detect_contract_artifacts_discovers_schema_dto_and_contract_files(tmp_path):
    # Canonical schema files
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text("model User { id String @id }", encoding="utf-8")
    (tmp_path / "openapi.json").write_text('{"openapi":"3.0.0","paths":{}}', encoding="utf-8")

    # DTO and contract-like files
    src = tmp_path / "src"
    src.mkdir()
    (src / "user.dto.ts").write_text("export type UserDto = { id: string }", encoding="utf-8")
    (src / "user.contract.ts").write_text("export const UserContract = {}", encoding="utf-8")

    profile = detect_all(tmp_path).to_dict()
    artifacts = profile.get("contract_artifacts", {})
    schema_files = artifacts.get("schema_files", [])
    dto_files = artifacts.get("dto_files", [])
    contract_files = artifacts.get("contract_files", [])

    assert "openapi.json" in schema_files
    assert "prisma/schema.prisma" in schema_files
    assert "src/user.dto.ts" in dto_files
    assert "src/user.contract.ts" in contract_files
