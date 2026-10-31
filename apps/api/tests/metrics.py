"""The app's OpenTelemetry metrics, as tests read them: one in-memory reader for the whole run,
as the global meter provider can be set only once. Instruments made before it was set report to
it all the same. Counters add up over the run, so a test compares before and after."""

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint

READER = InMemoryMetricReader()
metrics.set_meter_provider(MeterProvider(metric_readers=[READER]))

type Totals = dict[frozenset[tuple[str, object]], int | float]


def totals(name: str) -> Totals:
    """The running total of the counter ``name`` for each set of attributes it was given."""
    found: Totals = {}
    data = READER.get_metrics_data()
    if data is None:
        return found
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    if isinstance(point, NumberDataPoint):
                        found[frozenset((point.attributes or {}).items())] = point.value
    return found


def added(before: Totals, after: Totals, **attributes: object) -> int | float:
    """How much was added between two readings for the attributes given."""
    key = frozenset(attributes.items())
    return after.get(key, 0) - before.get(key, 0)
