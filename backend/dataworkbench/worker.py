from __future__ import annotations

from pathlib import Path
from typing import Any


def worker_ready_job() -> bool:
    """Small startup probe used to spawn the frozen worker on the main thread."""
    return True


def execute_pipeline_job(
    project_root: str,
    pipeline: dict[str, Any],
    preview: bool,
    target_node_id: str | None,
    preview_limit: int,
    preview_page: int = 1,
    execution_variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute CPU/data-heavy work outside the WebView host process."""
    from dataworkbench.engine import PipelineEngine
    from dataworkbench.registry import PluginRegistry

    root = Path(project_root)
    registry = PluginRegistry([root / "plugins_external"])
    engine = PipelineEngine(registry)
    return engine.execute(
        pipeline,
        preview=preview,
        target_node_id=target_node_id,
        preview_limit=preview_limit,
        preview_page=preview_page,
        execution_variables=execution_variables,
        project_dir=root,
    )


def list_mysql_databases_job(config: dict[str, Any]) -> list[str]:
    import pymysql
    from dataworkbench.mysql_utils import mysql_connect_kwargs

    connection = pymysql.connect(**mysql_connect_kwargs(config))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            return [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()


def list_mysql_tables_job(config: dict[str, Any]) -> list[str]:
    import pymysql
    from dataworkbench.mysql_utils import mysql_connect_kwargs

    connection = pymysql.connect(**mysql_connect_kwargs(config, database=str(config.get("database", ""))))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
            return [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()
