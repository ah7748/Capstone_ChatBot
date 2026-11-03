"""Métricas en memoria con salida en formato de texto Prometheus (sin dependencias externas).

Cada instancia del servidor lleva sus propios contadores; el recolector (Prometheus, Grafana
Agent, etc.) las agrega por instancia. Las etiquetas son de cardinalidad acotada a propósito
(ruta como plantilla, nunca el id concreto).
"""
import threading

DEFAULT_BUCKETS = (0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


class Registry:
    def __init__(self) -> None:
        self._metrics: list = []

    def register(self, metric) -> None:
        if any(m.name == metric.name for m in self._metrics):
            raise ValueError(f"métrica duplicada: {metric.name}")
        self._metrics.append(metric)

    def render(self) -> str:
        lines: list[str] = []
        for m in self._metrics:
            lines.append(f"# HELP {m.name} {m.help}")
            lines.append(f"# TYPE {m.name} {m.type}")
            lines.extend(m.samples())
        return "\n".join(lines) + "\n"


REGISTRY = Registry()


def _escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _number(value: int | float) -> str:
    return str(value) if isinstance(value, int) else repr(float(value))


class _Metric:
    type = ""

    def __init__(self, name: str, help: str, labelnames: tuple[str, ...] = (),
                 registry: Registry = REGISTRY) -> None:
        self.name, self.help, self.labelnames = name, help, tuple(labelnames)
        self._lock = threading.Lock()
        registry.register(self)

    def _key(self, labels: dict) -> tuple[str, ...]:
        if set(labels) != set(self.labelnames):
            raise ValueError(f"{self.name}: se esperaban las etiquetas {self.labelnames}, llegaron {tuple(labels)}")
        return tuple(str(labels[n]) for n in self.labelnames)

    def _labels(self, key: tuple[str, ...], extra: tuple[tuple[str, str], ...] = ()) -> str:
        pairs = list(zip(self.labelnames, key)) + list(extra)
        if not pairs:
            return ""
        return "{" + ",".join(f'{k}="{_escape(v)}"' for k, v in pairs) + "}"


class Counter(_Metric):
    type = "counter"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._values: dict[tuple[str, ...], int | float] = {}

    def inc(self, amount: int | float = 1, **labels) -> None:
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + amount

    def get(self, **labels) -> int | float:
        return self._values.get(self._key(labels), 0)

    def samples(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
        if not items and not self.labelnames:
            return [f"{self.name} 0"]
        return [f"{self.name}{self._labels(k)} {_number(v)}" for k, v in items]


class Histogram(_Metric):
    type = "histogram"

    def __init__(self, name: str, help: str, labelnames: tuple[str, ...] = (),
                 buckets: tuple[float, ...] = DEFAULT_BUCKETS, registry: Registry = REGISTRY) -> None:
        super().__init__(name, help, labelnames, registry)
        self.buckets = tuple(sorted(buckets))
        # por clave: [conteos por bucket..., suma, total]
        self._data: dict[tuple[str, ...], list] = {}

    def observe(self, value: float, **labels) -> None:
        key = self._key(labels)
        with self._lock:
            row = self._data.setdefault(key, [0] * len(self.buckets) + [0.0, 0])
            for i, upper in enumerate(self.buckets):
                if value <= upper:
                    row[i] += 1
            row[-2] += value
            row[-1] += 1

    def count(self, **labels) -> int:
        row = self._data.get(self._key(labels))
        return row[-1] if row else 0

    def total(self, **labels) -> float:
        row = self._data.get(self._key(labels))
        return row[-2] if row else 0.0

    def samples(self) -> list[str]:
        with self._lock:
            items = sorted((k, list(v)) for k, v in self._data.items())
        out: list[str] = []
        for key, row in items:
            for i, upper in enumerate(self.buckets):
                out.append(f"{self.name}_bucket{self._labels(key, (('le', repr(upper)),))} {row[i]}")
            out.append(f"{self.name}_bucket{self._labels(key, (('le', '+Inf'),))} {row[-1]}")
            out.append(f"{self.name}_sum{self._labels(key)} {_number(row[-2])}")
            out.append(f"{self.name}_count{self._labels(key)} {row[-1]}")
        return out


# ---- Métricas de la aplicación -------------------------------------------------------------
HTTP_REQUESTS = Counter("http_requests_total", "Peticiones HTTP atendidas.",
                        ("method", "route", "status"))
HTTP_DURATION = Histogram("http_request_duration_seconds", "Duración de las peticiones HTTP.",
                          ("method", "route"))
UNHANDLED_EXCEPTIONS = Counter("app_unhandled_exceptions_total", "Excepciones no controladas (HTTP 500).")
LLM_REQUESTS = Counter("llm_requests_total", "Llamadas al proveedor de IA por resultado.", ("outcome",))
LLM_DURATION = Histogram("llm_request_duration_seconds", "Duración de las llamadas al proveedor de IA.",
                         buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0))
LLM_TOKENS = Counter("llm_tokens_total", "Tokens consumidos en llamadas al proveedor de IA.")


def render() -> str:
    return REGISTRY.render()
