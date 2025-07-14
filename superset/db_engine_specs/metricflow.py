# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
An interface to dbt's semantic layer, Metric Flow.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, TypedDict

from shillelagh.backends.apsw.dialects.base import get_adapter_for_table_name

from superset.constants import TimeGrain
from superset.db_engine_specs.base import ValidColumnsType
from superset.db_engine_specs.shillelagh import ShillelaghEngineSpec
from superset.extensions.metricflow import TABLE_NAME
from superset.models.helpers import ExploreMixin
from superset.superset_typing import ResultSetColumnType

if TYPE_CHECKING:
    from sqlalchemy.engine.reflection import Inspector

    from superset.models.core import Database
    from superset.sql_parse import Table


SELECT_STAR_MESSAGE = (
    'The dbt semantic layer does not support data preview, since the "metrics" table '
    "is a virtual table that is not materialized. An administrator should configure "
    'the database in Apache Superset so that the "Disable SQL Lab data preview '
    'queries" option under "Advanced" → "SQL Lab" is enabled.'
)


class MetricType(TypedDict, total=False):
    """
    Type for metrics returned by `get_metrics`.
    """

    metric_name: str
    expression: str
    verbose_name: str | None
    metric_type: str | None
    description: str | None
    d3format: str | None
    warning_text: str | None
    extra: str | None


class DbtMetricFlowEngineSpec(ShillelaghEngineSpec):
    """
    Engine for the the dbt semantic layer.
    """

    engine = "metricflow"
    engine_name = "dbt Metric Flow"
    sqlalchemy_uri_placeholder = (
        "metricflow://[ab123.us1.dbt.com]/<environment_id>"
        "?service_token=<service_token>"
    )

    supports_dynamic_columns = True

    _time_grain_expressions = {
        TimeGrain.DAY: "{col}__day",
        TimeGrain.WEEK: "{col}__week",
        TimeGrain.MONTH: "{col}__month",
        TimeGrain.QUARTER: "{col}__quarter",
        TimeGrain.YEAR: "{col}__year",
    }

    @classmethod
    def select_star(cls, *args: Any, **kwargs: Any) -> str:
        """
        Return a ``SELECT *`` query.
        """
        message = SELECT_STAR_MESSAGE.replace("'", "''")
        return f"SELECT '{message}' AS warning"

    @classmethod
    def get_columns(
        cls,
        inspector: Inspector,
        table: Table,
        options: dict[str, Any] | None = None,
    ) -> list[ResultSetColumnType]:
        """
        Get columns.

        This method enriches the method from the SQLAlchemy dialect to include the
        dimension descriptions.
        """
        connection = inspector.engine.connect()
        adapter = get_adapter_for_table_name(connection, table.table)

        return [
            {
                "name": column["name"],
                "column_name": column["name"],
                "type": column["type"],
                "nullable": column["nullable"],
                "default": column["default"],
                "comment": adapter.dimensions.get(column["name"], ""),
            }
            for column in inspector.get_columns(table.table, table.schema)
        ]

    @classmethod
    def get_metrics(
        cls,
        database: Database,
        inspector: Inspector,
        table: Table,
    ) -> list[MetricType]:
        """
        Get all metrics.
        """
        connection = inspector.engine.connect()
        adapter = get_adapter_for_table_name(connection, table.table)

        return [
            {
                "metric_name": metric,
                "expression": metric,
                "description": description,
            }
            for metric, description in adapter.metrics.items()
        ]

    @classmethod
    def get_valid_columns(
        cls,
        database: Database,
        datasource: ExploreMixin,
        columns: set[str],
        metrics: set[str],
    ) -> ValidColumnsType:
        """
        Get valid columns.

        Given a datasource, and sets of selected metrics and dimensions, return the
        sets of valid metrics and dimensions that can further be selected.
        """
        with database.get_sqla_engine() as engine:
            connection = engine.connect()
            adapter = get_adapter_for_table_name(connection, TABLE_NAME)

        return {
            "metrics": adapter._get_metrics_for_dimensions(columns),
            "dimensions": adapter._get_dimensions_for_metrics(metrics),
        }
