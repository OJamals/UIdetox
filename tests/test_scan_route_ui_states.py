from uidetox.commands.scan import _collect_route_ui_state_issues


def test_collect_route_state_issues_flags_missing_loading_error_empty(tmp_path):
    route_file = tmp_path / "app" / "users" / "page.tsx"
    route_file.parent.mkdir(parents=True)
    route_file.write_text(
        'import { useQuery } from "@tanstack/react-query";\n'
        "export function UsersPage() {\n"
        '  const { data } = useQuery({ queryKey: ["users"] });\n'
        "  return <div>{data?.map((u) => <p key={u.id}>{u.name}</p>)}</div>;\n"
        "}\n",
        encoding="utf-8",
    )

    issues = _collect_route_ui_state_issues(
        str(tmp_path),
        exclude_paths=[],
        zone_overrides={},
        ignore_patterns=[],
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue["tier"] == "T2"
    assert "loading" in issue["issue"]
    assert "error" in issue["issue"]
    assert "empty" in issue["issue"]


def test_collect_route_state_issues_skips_non_route_fetching_file(tmp_path):
    non_route = tmp_path / "src" / "api" / "client.ts"
    non_route.parent.mkdir(parents=True)
    non_route.write_text(
        "export async function getUsers() {\n"
        '  return fetch("/api/users");\n'
        "}\n",
        encoding="utf-8",
    )

    issues = _collect_route_ui_state_issues(
        str(tmp_path),
        exclude_paths=[],
        zone_overrides={},
        ignore_patterns=[],
    )

    assert issues == []


def test_collect_route_state_issues_passes_complete_route(tmp_path):
    route_file = tmp_path / "pages" / "dashboard.tsx"
    route_file.parent.mkdir(parents=True)
    route_file.write_text(
        'import { useQuery } from "@tanstack/react-query";\n'
        "export default function Dashboard() {\n"
        '  const { data, isLoading, isError } = useQuery({ queryKey: ["stats"] });\n'
        "  if (isLoading) return <Skeleton />;\n"
        "  if (isError) return <ErrorFallback />;\n"
        "  if (!data || data.length === 0) return <EmptyState />;\n"
        "  return <section>{data.map((x) => <span key={x.id}>{x.name}</span>)}</section>;\n"
        "}\n",
        encoding="utf-8",
    )

    issues = _collect_route_ui_state_issues(
        str(tmp_path),
        exclude_paths=[],
        zone_overrides={},
        ignore_patterns=[],
    )

    assert issues == []
