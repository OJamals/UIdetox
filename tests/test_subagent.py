import pytest
from pathlib import Path

from uidetox import memory as memory_module
from uidetox import state as state_module
from uidetox.state import ensure_uidetox_dir, load_state
from uidetox.subagent import (
    REVIEW_DOMAINS,
    SCORED_REVIEW_DOMAINS,
    PERFECTION_GATE,
    REVIEW_WAVE_1,
    REVIEW_WAVE_2,
    _issue_group_workload,
    _shard_issue_groups_by_workload,
    _shard_items,
    _shard_items_by_workload,
    create_session,
    generate_stage_prompt,
    get_session,
    record_result,
)


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_module._project_root_cache = None
    # Clear managed ChromaDB clients so each test gets a fresh state
    memory_module._chroma_clients.clear()
    ensure_uidetox_dir()
    yield
    state_module._project_root_cache = None
    memory_module._chroma_clients.clear()


def test_shard_items_balances_workload_round_robin():
    shards = _shard_items([1, 2, 3, 4, 5], 3)
    assert shards == [[1, 4], [2, 5], [3]]


def _mk_group(file: str, tier: str, count: int) -> list[dict]:
    return [
        {
            "id": f"{Path(file).stem}-{idx}",
            "file": file,
            "tier": tier,
            "issue": f"{tier} issue {idx}",
            "command": "fix",
        }
        for idx in range(count)
    ]


def test_shard_issue_groups_by_workload_reduces_skew_vs_round_robin():
    groups = [
        _mk_group("src/A.tsx", "T1", 9),  # heavy
        _mk_group("src/B.tsx", "T1", 1),
        _mk_group("src/C.tsx", "T2", 2),
        _mk_group("src/D.tsx", "T2", 2),
        _mk_group("src/E.tsx", "T2", 2),
        _mk_group("src/F.tsx", "T2", 2),
    ]
    rr = _shard_items(groups, 2)
    weighted = _shard_issue_groups_by_workload(groups, 2)

    def load(shard: list[list[dict]]) -> int:
        return sum(_issue_group_workload(group) for group in shard)

    rr_spread = max(load(s) for s in rr) - min(load(s) for s in rr)
    weighted_spread = max(load(s) for s in weighted) - min(load(s) for s in weighted)
    assert weighted_spread < rr_spread


def test_fullstack_prompt_includes_contract_artifacts():
    from uidetox.state import save_config

    save_config(
        {
            "tooling": {
                "backend": [{"name": "nest"}],
                "database": [{"name": "prisma"}],
                "api": [{"name": "rest"}],
                "contract_artifacts": {
                    "schema_files": ["openapi.json"],
                    "dto_files": ["src/types/user.dto.ts"],
                    "contract_files": ["src/contracts/user.contract.ts"],
                },
            }
        }
    )
    prompt = generate_stage_prompt("observe", parallel=1)[0]
    assert "openapi.json" in prompt
    assert "src/types/user.dto.ts" in prompt
    assert "src/contracts/user.contract.ts" in prompt


def test_fullstack_prompt_fallback_without_contract_artifacts():
    from uidetox.state import save_config

    save_config(
        {
            "tooling": {
                "backend": [{"name": "nest"}],
                "database": [{"name": "prisma", "config_file": "prisma/schema.prisma"}],
                "api": [{"name": "rest", "config_file": "openapi.json"}],
            }
        }
    )
    prompt = generate_stage_prompt("diagnose", parallel=1)[0]
    assert "prisma/schema.prisma" in prompt
    assert "openapi.json" in prompt


def test_stage_prompt_injects_gitnexus_repo_flags_when_configured():
    from uidetox.state import save_config

    save_config({"gitnexus_repo": "UIdetox"})
    prompt = generate_stage_prompt("diagnose", parallel=1)[0]

    assert "npx gitnexus query -r UIdetox" in prompt
    assert "npx gitnexus context -r UIdetox <component_name>" in prompt
    assert "npx gitnexus impact -r UIdetox <component_name>" in prompt


def test_record_result_clears_stale_review_request_when_confidence_recovers():
    session_id = create_session("verify", "verify prompt")
    assert record_result(session_id, {"note": "manual check required", "confidence": 0.6}) is True

    session_dir = ensure_uidetox_dir() / "sessions" / f"session_{session_id}"
    assert (session_dir / "review_request.json").exists()

    assert record_result(session_id, {"note": "all checks passed", "confidence": 0.95}) is True
    assert not (session_dir / "review_request.json").exists()

    session = get_session(session_id)
    assert session is not None
    assert session["meta"]["status"] == "completed"


def test_record_result_ingests_structured_issues_into_queue():
    session_id = create_session("review", "review prompt")
    payload = {
        "confidence": 0.93,
        "issues": [
            {
                "file": "src/components/Table.tsx",
                "severity": "high",
                "description": "Missing empty-state UX for zero rows",
                "fix_command": "uidetox harden src/components/Table.tsx",
            }
        ],
    }

    assert record_result(session_id, payload) is True
    state = load_state()
    issues = state.get("issues", [])
    assert len(issues) == 1
    issue = issues[0]
    assert issue["file"] == "src/components/Table.tsx"
    assert issue["tier"] == "T2"
    assert "Missing empty-state UX" in issue["issue"]
    assert issue["command"] == "uidetox harden src/components/Table.tsx"
    assert issue.get("phase") == "subagent_review"


def test_record_result_extracts_add_issue_commands_from_output_text():
    session_id = create_session("verify", "verify prompt")
    payload = {
        "confidence": 0.9,
        "output": (
            'uidetox add-issue --file src/App.tsx --tier T3 '
            '--issue "Missing loading skeleton" '
            '--fix-command "uidetox harden src/App.tsx"'
        ),
    }

    assert record_result(session_id, payload) is True
    state = load_state()
    issues = state.get("issues", [])
    assert len(issues) == 1
    issue = issues[0]
    assert issue["file"] == "src/App.tsx"
    assert issue["tier"] == "T3"
    assert issue["issue"] == "Missing loading skeleton"
    assert issue["command"] == "uidetox harden src/App.tsx"
    assert issue.get("phase") == "subagent_verify"


def test_record_result_dedupes_repeated_ingested_issues():
    session_id = create_session("review", "review prompt")
    payload = {
        "confidence": 0.92,
        "issues": [
            {
                "file": "src/components/Card.tsx",
                "tier": "T2",
                "issue": "Inconsistent focus ring contrast",
                "fix_command": "uidetox polish src/components/Card.tsx",
            }
        ],
    }

    assert record_result(session_id, payload) is True
    assert record_result(session_id, payload) is True

    state = load_state()
    matches = [
        i for i in state.get("issues", [])
        if i.get("file") == "src/components/Card.tsx"
        and "focus ring contrast" in i.get("issue", "")
    ]
    assert len(matches) == 1


def test_parallel_review_prompts_keep_global_file_scope_per_domain():
    src = Path("src")
    src.mkdir(parents=True, exist_ok=True)
    file_a = (src / "Alpha.tsx").resolve()
    file_b = (src / "Beta.tsx").resolve()
    file_a.write_text("export const Alpha = () => null;\n", encoding="utf-8")
    file_b.write_text("export const Beta = () => null;\n", encoding="utf-8")

    prompts = generate_stage_prompt("review", parallel=2)
    assert len(prompts) == 2
    for prompt in prompts:
        assert str(file_a) in prompt
        assert str(file_b) in prompt


class TestReviewDomains:
    """Verify the 10 scored review domains (2 waves of 5) plus perfection gate."""

    def test_review_domains_has_fifteen_entries(self):
        """14 scored domains + 1 perfection gate = 15 total."""
        assert len(REVIEW_DOMAINS) == 15

    def test_scored_review_domains_has_fourteen_entries(self):
        assert len(SCORED_REVIEW_DOMAINS) == 14

    def test_wave_1_has_seven_entries(self):
        assert len(REVIEW_WAVE_1) == 7

    def test_wave_2_has_seven_entries(self):
        assert len(REVIEW_WAVE_2) == 7

    def test_waves_cover_all_scored_domains(self):
        """Wave 1 + Wave 2 should equal all scored domains."""
        assert len(REVIEW_WAVE_1) + len(REVIEW_WAVE_2) == len(SCORED_REVIEW_DOMAINS)

    def test_each_domain_has_required_keys(self):
        required = {"name", "label", "references", "rubric", "focus", "wave",
                     "max_score", "checklist", "thresholds", "deductions"}
        for domain in REVIEW_DOMAINS:
            assert required <= set(domain.keys()), f"Missing keys in {domain.get('name')}"

    def test_perfection_gate_exists(self):
        assert PERFECTION_GATE is not None
        assert PERFECTION_GATE["name"] == "perfection_gate"
        assert PERFECTION_GATE["max_score"] == 0
        assert PERFECTION_GATE["wave"] == 0
        assert len(PERFECTION_GATE["checklist"]) >= 10

    def test_each_scored_domain_has_positive_max_score(self):
        for domain in SCORED_REVIEW_DOMAINS:
            assert domain.get("max_score", 0) > 0, f"{domain['name']} has no max_score"

    def test_scored_domain_max_scores_sum_to_expected(self):
        """All scored domain max scores should sum to 138 for proper normalization."""
        total = sum(d.get("max_score", 0) for d in SCORED_REVIEW_DOMAINS)
        assert total == 138, f"Total max scores = {total}, expected 138"

    def test_each_scored_domain_has_non_empty_checklist(self):
        for domain in SCORED_REVIEW_DOMAINS:
            checklist = domain.get("checklist", [])
            assert len(checklist) >= 3, (
                f"{domain['name']} has only {len(checklist)} checklist items"
            )

    def test_each_scored_domain_has_deductions(self):
        for domain in SCORED_REVIEW_DOMAINS:
            deductions = domain.get("deductions", [])
            assert len(deductions) >= 2, (
                f"{domain['name']} has only {len(deductions)} deduction rules"
            )

    def test_parallel_review_generates_fourteen_prompts(self):
        """Parallel=14 should produce one prompt per review domain."""
        prompts = generate_stage_prompt("review", parallel=14)
        assert len(prompts) == 14

    def test_parallel_seven_generates_seven_prompts(self):
        """Parallel=7 should shard 14 domains into 7 prompts (2 domains each)."""
        prompts = generate_stage_prompt("review", parallel=7)
        assert len(prompts) == 7

    def test_parallel_review_prompts_reference_gitnexus(self):
        """Each domain review prompt should include gitnexus instructions."""
        prompts = generate_stage_prompt("review", parallel=14)
        for prompt in prompts:
            assert "gitnexus" in prompt.lower(), "Review prompt missing gitnexus instruction"

    def test_parallel_review_prompts_reference_check_fix(self):
        """Each domain review prompt should instruct pre-commit checks."""
        prompts = generate_stage_prompt("review", parallel=14)
        for prompt in prompts:
            assert "check --fix" in prompt, "Review prompt missing check --fix instruction"

    def test_parallel_review_prompts_include_checklist(self):
        """Each domain review prompt should include verification checklist items."""
        prompts = generate_stage_prompt("review", parallel=14)
        for prompt in prompts:
            assert "Verification Checklist" in prompt, "Review prompt missing checklist"

    def test_parallel_review_prompts_include_deductions(self):
        """Each domain review prompt should include automatic deduction rules."""
        prompts = generate_stage_prompt("review", parallel=14)
        for prompt in prompts:
            assert "Automatic Deductions" in prompt, "Review prompt missing deductions"

    def test_parallel_review_prompts_include_scoring_protocol(self):
        """Each domain review prompt should include the scoring protocol."""
        prompts = generate_stage_prompt("review", parallel=14)
        for prompt in prompts:
            assert "Scoring Protocol" in prompt, "Review prompt missing scoring protocol"

    def test_parallel_review_prompts_show_max_score(self):
        """Each domain review prompt should display the max score for its domains."""
        prompts = generate_stage_prompt("review", parallel=14)
        for prompt in prompts:
            assert "Max Score" in prompt or "max" in prompt.lower(), "Review prompt missing max score"

    def test_single_review_prompt_includes_all_domains(self):
        """Non-parallel review prompt should include all 10 domain rubrics."""
        prompts = generate_stage_prompt("review", parallel=1)
        assert len(prompts) == 1
        prompt = prompts[0]
        for domain in REVIEW_DOMAINS:
            assert domain["label"] in prompt, f"Single review missing domain {domain['label']}"

    def test_single_review_prompt_references_gitnexus(self):
        """Non-parallel review prompt should include gitnexus instructions."""
        prompts = generate_stage_prompt("review", parallel=1)
        assert len(prompts) == 1
        assert "gitnexus analyze" in prompts[0]

    def test_domain_names_cover_expected_areas(self):
        """The 14 domains should cover all expected design areas."""
        names = {d["name"] for d in REVIEW_DOMAINS}
        # Wave 1
        assert "typography" in names
        assert "color_contrast" in names
        assert "interaction_states" in names
        assert "content_ux_writing" in names
        assert "motion_animation" in names
        assert "design_elegance" in names
        assert "accessibility" in names
        # Wave 2
        assert "spatial_layout" in names
        assert "materiality_surfaces" in names
        assert "consistency_system" in names
        assert "identity_brand" in names
        assert "architecture_responsive" in names
        assert "api_data_coherence" in names
        assert "performance_vitals" in names

    def test_api_data_coherence_enforces_contract_and_database_alignment(self):
        domain = next(d for d in REVIEW_DOMAINS if d["name"] == "api_data_coherence")
        checklist_text = " ".join(domain.get("checklist", [])).lower()
        thresholds = domain.get("thresholds", {})
        deductions_text = " ".join(domain.get("deductions", [])).lower()

        assert "contract" in checklist_text
        assert "database" in checklist_text
        assert "contract_artifact_coverage" in thresholds
        assert "endpoint_mapping_coverage" in thresholds
        assert "stale" in deductions_text or "invalidate" in deductions_text

    def test_perfection_gate_checks_contract_drift(self):
        checklist = [str(item).lower() for item in PERFECTION_GATE.get("checklist", [])]
        assert any("contract drift" in item or "api/db" in item for item in checklist)

    def test_wave_assignments_correct(self):
        """Wave 1 domains should have wave=1, wave 2 should have wave=2."""
        for d in REVIEW_WAVE_1:
            assert d.get("wave") == 1, f"{d['name']} should be wave 1"
        for d in REVIEW_WAVE_2:
            assert d.get("wave") == 2, f"{d['name']} should be wave 2"


class TestScoringWeight:
    """Verify the blended score uses 70% subjective / 30% objective."""

    def test_blended_score_weight(self):
        from uidetox.utils import compute_design_score

        state = {
            "issues": [],
            "resolved": [{"tier": "T1"}, {"tier": "T2"}],
            "stats": {"scans_run": 1},
            "subjective": {"score": 80},
        }
        scores = compute_design_score(state)
        # Objective = 100 (all resolved), Subjective raw = 80
        # Curve compresses raw 80: effective ≈ 74
        # Blended = 100 * 0.3 + effective * 0.7 < 86
        assert scores["blended_score"] < 86, (
            f"Curve should compress: raw sub 80 -> effective "
            f"{scores.get('effective_subjective')}, blended {scores['blended_score']}"
        )
        # But still reasonable (not catastrophically low)
        assert scores["blended_score"] >= 75
        # Objective should still be 100
        assert scores["objective_score"] == 100
        assert scores["objective_score"] == 100
        assert scores["subjective_score"] == 80

    def test_subjective_dominates_when_objective_perfect(self):
        from uidetox.utils import compute_design_score

        state = {
            "issues": [],
            "resolved": [{"tier": "T1"}],
            "stats": {"scans_run": 1},
            "subjective": {"score": 50},
        }
        scores = compute_design_score(state)
        # 100 * 0.3 + 50 * 0.7 = 30 + 35 = 65
        assert scores["blended_score"] == 65


class TestPromptGitnexusInstructions:
    """Verify all subagent stage prompts include gitnexus CLI instructions."""

    def test_observe_prompt_has_gitnexus(self):
        prompts = generate_stage_prompt("observe", parallel=1)
        assert any("gitnexus" in p.lower() for p in prompts)

    def test_fix_prompt_has_gitnexus(self):
        from uidetox.state import save_state
        save_state({
            "issues": [{"id": "FIX-1", "file": "src/App.tsx", "tier": "T1",
                         "issue": "test", "command": "test"}],
            "resolved": [],
            "stats": {"scans_run": 1},
        })
        prompts = generate_stage_prompt("fix", parallel=1)
        assert any("gitnexus" in p.lower() for p in prompts)

    def test_verify_prompt_has_gitnexus(self):
        prompts = generate_stage_prompt("verify", parallel=1)
        assert any("gitnexus" in p.lower() or "detect_changes" in p for p in prompts)


class TestAutofixSnapshot:
    """Verify the autofix file snapshot/rollback mechanism."""

    def test_snapshot_captures_and_restores(self, tmp_path):
        from uidetox.commands.autofix import _FileSnapshot

        test_file = tmp_path / "test.tsx"
        test_file.write_text("original content")

        snapshot = _FileSnapshot(str(tmp_path))
        snapshot.capture([str(test_file)])
        assert snapshot.file_count == 1

        # Modify the file
        test_file.write_text("modified content")
        assert test_file.read_text() == "modified content"

        # Rollback
        restored = snapshot.restore()
        assert restored == 1
        assert test_file.read_text() == "original content"

    def test_snapshot_handles_nonexistent_file(self, tmp_path):
        from uidetox.commands.autofix import _FileSnapshot

        missing = tmp_path / "does_not_exist.tsx"
        snapshot = _FileSnapshot(str(tmp_path))
        snapshot.capture([str(missing)])
        assert snapshot.file_count == 1  # Missing files are tracked for rollback safety

        # If the file is created later, restore() should remove it.
        missing.write_text("new content")
        restored = snapshot.restore()
        assert restored == 1
        assert not missing.exists()

    def test_snapshot_captures_multiple_files(self, tmp_path):
        from uidetox.commands.autofix import _FileSnapshot

        files = []
        for i in range(5):
            f = tmp_path / f"file_{i}.tsx"
            f.write_text(f"content {i}")
            files.append(str(f))

        snapshot = _FileSnapshot(str(tmp_path))
        snapshot.capture(files)
        assert snapshot.file_count == 5

        # Modify all
        for i, f in enumerate(files):
            Path(f).write_text(f"modified {i}")

        # Rollback
        restored = snapshot.restore()
        assert restored == 5
        for i, f in enumerate(files):
            assert Path(f).read_text() == f"content {i}"


class TestBatchResolvePreFlight:
    """Verify batch-resolve pre-flight validation."""

    def test_preflight_warns_on_missing_files(self):
        from uidetox.commands.batch_resolve import _preflight_validate
        from uidetox.state import save_state

        save_state({
            "issues": [
                {"id": "TEST-1", "file": "/nonexistent/path/component.tsx",
                 "tier": "T1", "issue": "test", "command": "test"}
            ],
            "resolved": [],
            "stats": {"scans_run": 1},
        })

        warnings = _preflight_validate(["TEST-1"], {"auto_commit": False})
        assert any("not found" in w.lower() for w in warnings)

    def test_preflight_no_warnings_on_valid_state(self, tmp_path):
        from uidetox.commands.batch_resolve import _preflight_validate
        from uidetox.state import save_state

        test_file = tmp_path / "component.tsx"
        test_file.write_text("<div>test</div>")

        save_state({
            "issues": [
                {"id": "TEST-2", "file": str(test_file),
                 "tier": "T1", "issue": "test issue", "command": "test"}
            ],
            "resolved": [],
            "stats": {"scans_run": 1},
        })

        warnings = _preflight_validate(["TEST-2"], {"auto_commit": False})
        # Should have no file-not-found warnings for existing files
        file_warnings = [w for w in warnings if "not found" in w.lower()]
        assert len(file_warnings) == 0


# ── Workload-aware sharding tests ────────────────────────────────


class TestWorkloadAwareSharding:
    """Verify complexity-based sharding distributes files by estimated workload."""

    def test_basic_workload_sharding(self, tmp_path):
        """Files in different dirs should be distributed across shards."""
        # Put files in different directories to avoid co-directory coupling
        d1 = tmp_path / "components"
        d2 = tmp_path / "pages"
        d3 = tmp_path / "utils"
        d1.mkdir(); d2.mkdir(); d3.mkdir()
        (d1 / "small.tsx").write_text("x\n" * 50, encoding="utf-8")
        (d2 / "medium.tsx").write_text("x\n" * 500, encoding="utf-8")
        (d3 / "large.tsx").write_text("x\n" * 2000, encoding="utf-8")

        files = [str(d1 / "small.tsx"), str(d2 / "medium.tsx"), str(d3 / "large.tsx")]
        shards = _shard_items_by_workload(files, 2)

        assert len(shards) == 2
        flat = [f for shard in shards for f in shard]
        assert set(flat) == set(files)

    def test_empty_files(self):
        shards = _shard_items_by_workload([], 3)
        assert shards == []

    def test_single_file(self, tmp_path):
        f = tmp_path / "only.tsx"
        f.write_text("content", encoding="utf-8")
        shards = _shard_items_by_workload([str(f)], 3)
        assert len(shards) == 1
        assert shards[0] == [str(f)]

    def test_parallel_exceeds_files(self, tmp_path):
        for i in range(2):
            (tmp_path / f"f{i}.tsx").write_text("x", encoding="utf-8")
        files = [str(tmp_path / f"f{i}.tsx") for i in range(2)]
        shards = _shard_items_by_workload(files, 10)
        assert len(shards) <= 2

    def test_preserves_all_files(self, tmp_path):
        for i in range(7):
            (tmp_path / f"comp{i}.tsx").write_text("a" * (100 * (i + 1)), encoding="utf-8")
        files = [str(tmp_path / f"comp{i}.tsx") for i in range(7)]
        shards = _shard_items_by_workload(files, 3)
        flat = sorted([f for s in shards for f in s])
        assert flat == sorted(files)

    def test_issue_density_affects_sharding(self, tmp_path):
        # Place files in different directories to avoid co-directory coupling
        dirs = [tmp_path / f"dir{i}" for i in range(4)]
        for d in dirs:
            d.mkdir()
        for i, d in enumerate(dirs):
            (d / f"c{i}.tsx").write_text("x\n" * 100, encoding="utf-8")
        files = [str(dirs[i] / f"c{i}.tsx") for i in range(4)]
        issues = [
            {"file": files[0], "tier": "T1", "issue": "issue1"},
            {"file": files[0], "tier": "T1", "issue": "issue2"},
            {"file": files[0], "tier": "T1", "issue": "issue3"},
        ]
        shards = _shard_items_by_workload(files, 2, issues=issues)
        assert len(shards) == 2
        flat = [f for s in shards for f in s]
        assert set(flat) == set(files)

    def test_round_robin_backward_compat(self):
        shards = _shard_items([1, 2, 3, 4, 5, 6], 3)
        assert shards == [[1, 4], [2, 5], [3, 6]]
