from __future__ import annotations

import inspect

from uidetox.contract_adapters import extract_backend_observations
from uidetox.frontend_map import FrontendMap, map_frontend
from uidetox.project_map import ProjectMap, build_project_map
from uidetox.prototype import build_prototype_brief
from uidetox.redesign import RedesignSet, propose_redesigns


def test_plan059_public_facade_signatures_are_frozen() -> None:
    assert {
        function.__name__: str(inspect.signature(function))
        for function in (
            extract_backend_observations,
            build_project_map,
            map_frontend,
            propose_redesigns,
            build_prototype_brief,
        )
    } == {
        "extract_backend_observations": (
            "(root: 'Path') -> 'tuple[list[ContractObservation], dict[str, Any]]'"
        ),
        "build_project_map": (
            "(root: 'str | Path', frontend_nodes: 'Iterable[Any]' = (), *, "
            "suppress_internal: 'bool' = True) -> 'ProjectMap'"
        ),
        "map_frontend": (
            "(root: 'str | Path', target: 'str | Path | None' = None, "
            "runtime: 'RuntimeObservation | None' = None) -> 'FrontendMap'"
        ),
        "propose_redesigns": (
            "(frontend_map: 'FrontendMap', brief: 'RedesignBrief | None' = None) "
            "-> 'RedesignSet'"
        ),
        "build_prototype_brief": (
            "(redesign_set: 'RedesignSet', proposal_id: 'str') -> 'str'"
        ),
    }


def test_plan059_legacy_artifact_loaders_keep_exact_contracts(tmp_path) -> None:
    project = ProjectMap.from_dict({})
    assert project.to_dict() == {
        "schema_version": 2,
        "nodes": [],
        "edges": [],
        "findings": [],
        "evidence": {},
    }

    frontend_payload = map_frontend(tmp_path).to_dict()
    frontend_payload.pop("project_map")
    loaded_frontend = FrontendMap.from_dict(frontend_payload)
    assert loaded_frontend.project_map == {}
    assert loaded_frontend.to_dict() == {**frontend_payload, "project_map": {}}

    for loader, expected_error in (
        (FrontendMap.from_dict, "Unsupported frontend map schema 0; expected 1."),
        (RedesignSet.from_dict, "Unsupported redesign schema 0; expected 2."),
    ):
        try:
            loader({})
        except ValueError as error:
            assert str(error) == expected_error
        else:  # pragma: no cover - contract guard
            raise AssertionError("legacy loader accepted an unsupported schema")
